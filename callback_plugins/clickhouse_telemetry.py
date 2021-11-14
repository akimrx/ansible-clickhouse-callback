import getpass
import json
import os
import re
import requests
import socket
import time

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ansible import context
from ansible.module_utils._text import to_text
from ansible.plugins.callback import CallbackBase

__metaclass__ = type

DATETIME_FMT = "%Y-%m-%d %H:%M:%S"
DATE_FMT = "%Y-%m-%d"
DOCUMENTATION = """
    callback: clickhouse_telemetry
    callback_type: aggregate
    short_description: send ansible events to Clickhouse storage over HTTP.
    author: "Akim Lindberg (@akimrx)"
    description:
      - This callback will report only stats events to Clickhouse.
    version_added: "2.9"
    requirements:
      - whitelisting in configuration
    options:
      clickhouse_url:
        description: Clickhouse URL and HTTP port. Like http://localhost:8123
        required: True
        env:
          - name: CLICKHOUSE_URL
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_url
      clickhouse_user:
        description: Clickhouse user used for authentication.
        required: False
        env:
          - name: CLICKHOUSE_USER
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_user
        default: default
      clickhouse_password:
        description: Clickhouse password used for authentication.
        required: False
        env:
          - name: CLICKHOUSE_PASSWORD
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_password
      clickhouse_database:
        description: Clickhouse database used for store.
        required: True
        env:
          - name: CLICKHOUSE_DATABASE
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_database
      clickhouse_logs_table:
        description: Clickhouse table used for store play logs.
        required: True
        env:
          - name: CLICKHOUSE_LOGS_TABLE
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_logs_table
      clickhouse_tasks_table:
        description: Clickhouse table used for store tasks duration.
        required: False
        env:
          - name: CLICKHOUSE_TASKS_TABLE
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_tasks_table
      clickhouse_timeout:
        description: Request execution waiting time.
        required: False
        env:
          - name: CLICKHOUSE_TIMEOUT
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_timeout
        default: 5
      clickhouse_pure_threshold:
        description: The percentage of playbook tasks that have not been modified to determine the startup from scratch (experimental).
        required: False
        env:
          - name: CLICKHOUSE_PURE_THRESHOLD
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_pure_threshold
        default: 75
      clickhouse_tz:
        description: Timezone.
        required: False
        env:
          - name: CLICKHOUSE_TZ
        ini:
          - section: callback_clickhouse_telemetry
            key: clickhouse_tz
      ansible_operator:
        description: The user who launched the playbook.
        required: False
        env:
          - name: ANSIBLE_OPERATOR
        ini:
          - section: callback_clickhouse_telemetry
            key: ansible_operator
"""


def get_playbook_branch_name():
    try:
        head_dir = Path(".") / ".git" / "HEAD"
        with head_dir.open("r") as f:
            content = f.read().splitlines()

        for line in content:
            if line[0:4] == "ref:":
                return line.partition("refs/heads/")[2]
    except Exception:
        return "unknown"


def format_playbook_name(playbook: str = None):
    if playbook is None:
        return "unknown"
    try:
        return re.sub(r"(\.yml|\.yaml)", "", playbook.split("/")[-1])
    except (IndexError, AttributeError):
        return playbook


def format_task_name(task):
    task_metadata = task.__dict__
    return dict(
        role=str(task_metadata.get("_role", "unknown")).lower(),
        name=str(task_metadata.get("_ds", {}).get("name", "gather facts")).lower(),
    )


def metadata():
    ctx = context.CLIARGS
    event_type = "check" if ctx.get("check") else "play"

    try:
        inventory = ", ".join(
            [inv.split("/")[-2] for inv in ctx.get("inventory", [])]
        )
    except IndexError:
        inventory = "unknown"

    return dict(
        tags=ctx.get("tags"),
        skipped_tags=ctx.get("skip_tags"),
        limit=ctx.get("subset"),
        event_type=event_type,
        inventory=inventory,
        extra_vars=ctx.get("extra_vars"),
        connection=ctx.get("connection"),
        forks=ctx.get("forks"),
    )


class CallbackModule(CallbackBase):
    """
    Ansible Clickhouse callback plugin
    ansible.cfg:
        callback_plugins   = <path_to_callback_plugins_folder>
        callback_whitelist = clickhouse_telemetry
    And put the plugin in <path_to_callback_plugins_folder>
    """

    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "clickhouse_telemetry"
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self, display=None):
        super(CallbackModule, self).__init__(display=display)

        for k, v in metadata().items():
            setattr(self, k, v)

        self.headers = {"Content-Type": "application/json"}
        self.branch = get_playbook_branch_name()
        self.hostname = socket.gethostname()
        self.start_time = datetime.now()
        self.unreachable_hosts = 0
        self.failed_hosts = 0
        self.ok = 0
        self.skipped = 0
        self.changed = 0
        self.task_stats = dict()
        self.current = None

    def set_options(self, task_keys=None, var_options=None, direct=None):
        super(CallbackModule, self).set_options(task_keys=task_keys, var_options=var_options, direct=direct)
        self.clickhouse_url = self.get_option("clickhouse_url")
        self.clickhouse_user = self.get_option("clickhouse_user") or "default"
        self.clickhouse_password = self.get_option("clickhouse_password") or None
        self.clickhouse_database = self.get_option("clickhouse_database")
        self.clickhouse_logs_table = self.get_option("clickhouse_logs_table")
        self.clickhouse_tasks_table = self.get_option("clickhouse_tasks_table") or None
        self.clickhouse_timeout = self.get_option("clickhouse_timeout") or 5
        self.clickhouse_pure_threshold = self.get_option("clickhouse_pure_threshold") or 75
        self.operator = self.get_option("ansible_operator") or getpass.getuser()
        self.clickhouse_tz = self.get_option("clickhouse_tz") or None

        if self.clickhouse_tz:
            os.environ["TZ"] = self.clickhouse_tz

    def v2_playbook_on_start(self, playbook):
        self.playbook = format_playbook_name(playbook._file_name)

    def v2_playbook_on_task_start(self, task, is_conditional):
        task_metadata = format_task_name(task)
        if self.current is not None:
            self.task_stats[self.current] = {
                "role": task_metadata.get("role"),
                "duration": "{:.03f}".format(
                    time.time() - self.task_stats[self.current]["duration"]
                ),
            }

        self.current = task_metadata.get("name")
        self.task_stats[self.current] = {
            "role": task_metadata.get("role"),
            "duration": time.time(),
        }

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.failed_hosts += 1

    def v2_runner_on_unreachable(self, result):
        self.unreachable_hosts += 1

    def v2_playbook_on_stats(self, stats):
        end_time = datetime.now()
        duration = end_time - self.start_time
        status = "success" if self.failed_hosts == 0 else "failed"
        hosts = sorted(stats.processed.keys())

        if self.current is not None:
            self.task_stats[self.current]["duration"] = "{:.03f}".format(
                time.time() - self.task_stats[self.current]["duration"]
            )

        tasks_payload = " ".join(
            json.dumps(task) for task in self._task_stats_batch()
        )
        event = dict(
            event_date=end_time.strftime(DATE_FMT),
            start_time=self.start_time.strftime(DATETIME_FMT),
            end_time=end_time.strftime(DATETIME_FMT),
            duration=int(duration.total_seconds()),
            user=self.operator,
            hostname=self.hostname,
            inventory=self.inventory,
            playbook=self.playbook,
            event_type=self.event_type,
            status=status,
            branch=self.branch,
            tags=self.tags,
            skipped_tags=self.skipped_tags,
            extra_vars=self.extra_vars,
            limit_expression=self.limit or "all",
            hosts=hosts,
            affected_hosts_count=len(hosts),
            unreachable_hosts_count=self.unreachable_hosts,
            failed_hosts_count=self.failed_hosts,
            connection_mode=self.connection,
            forks_count=self.forks,
            pure_play=self._pure_play(stats).get("is_pure", False),
        )

        self._send_event(
            self.clickhouse_database,
            self.clickhouse_logs_table,
            json.dumps(event)
        )

        if self.clickhouse_tasks_table:
            self._send_event(
                self.clickhouse_database,
                self.clickhouse_tasks_table,
                tasks_payload
            )

    def _send_event(self, db, table, events):
        url = f"{self.clickhouse_url}/?user={self.clickhouse_user}"
        if self.clickhouse_password:
            url += f"&password={self.clickhouse_password}"

        try:
            query = f"INSERT INTO {db}.{table} FORMAT JSONEachRow {events}"
            response = requests.post(
                url=url, headers=self.headers, data=query, timeout=int(self.clickhouse_timeout)
            )
        except Exception as error:
            self._display.warning(
                f"Could not submit event to Clickhouse: {to_text(error)}"
            )
        else:
            if not response.ok:
                self._display.warning(
                    f"Could not submit event to Clickhouse. "
                    f"Status: {response.status_code}. {response.text}"
                )

    def _task_stats_batch(self):
        batch = []
        for task, metrics in self.task_stats.items():
            batch.append({
                "event_date": self.start_time.strftime(DATE_FMT),
                "playbook": self.playbook,
                "user": self.operator,
                "role": metrics.get("role"),
                "task": task,
                "duration": int(Decimal(metrics.get("duration")) * 1000),
            })
        return batch

    def _pure_play(self, stats):
        for count in stats.ok.values():
            self.ok += count
        for count in stats.skipped.values():
            self.skipped += count
        for count in stats.changed.values():
            self.changed += count

        total = self.changed + self.ok
        try:
            percent_diff = (self.ok / total) * 100
        except ZeroDivisionError:
            percent_diff = 0

        return dict(
            is_pure=False if total > 0 and percent_diff >= int(self.clickhouse_pure_threshold) else True,
            percent=percent_diff,
            not_changed=self.ok,
            total_tasks=total,
        )
