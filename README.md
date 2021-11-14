# Ansible Clickhouse Telemetry
Plugin for sending telemetry from Ansible to Clickhouse storage


## Compability

This plugin was tested on version >= 2.9 with [a structure that is recommended by the community](https://docs.ansible.com/ansible/2.8/user_guide/playbooks_best_practices.html#alternative-directory-layout).

If the plugin does not work correctly with your structure or version, it is recommended to start an issue and provide details
* Your ansible directory structure
* Ansible version
* Configuration parameters for a plugin without sensitive data

## Installation

* Copy `clickhouse_telemetry.py` to the `callback_plugins` directory.

* Create database and tables in the Clickhouse:
    ```shell
    clickhouse-client < install.sql
    ```

* Update your `ansible.cfg`:
    ```ini
    [defaults]
    callback_plugins = /path/to/callback_plugins_dir
    callback_whitelist = clickhouse_telemetry


    [callback_clickhouse_telemetry]
    clickhouse_url = "http://localhost:8123"
    clickhouse_user = "ansible"
    clickhouse_password = "strong_password"
    clickhouse_database = "ansible"
    clilckhouse_logs_table = "logs"
    clickhouse_tasks_table = "tasks"
    clickhouse_timeout = 5
    clickhouse_pure_threshold = 80
    clickhouse_tz = "Europe/Moscow"
    ansible_operator = "username"
    ```


## Example data

### Logs
```sql
SELECT *
FROM `ansible`.`logs`
ORDER BY event_date DESC
LIMIT 1
FORMAT Vertical

Row 1:
──────
event_date:              2021-11-14
start_time:              2021-11-14 11:41:55
end_time:                2021-11-14 11:42:16
duration:                20
user:                    akimrx
hostname:                macbook-pro
inventory:               test
playbook:                bootstrap
event_type:              play
status:                  success
branch:                  master
tags:                    ['firewall']
skipped_tags:            []
extra_vars:              []
limit_expression:        srv*
hosts:                   ['srv01-yndx.akimrx.cloud', 'srv02-yndx.akimrx.cloud']
affected_hosts_count:    2
unreachable_hosts_count: 0
failed_hosts_count:      0
connection_mode:         smart
forks_count:             30
pure_play:               0

1 rows in set. Elapsed: 0.003 sec. 
```

### Tasks
```sql
SELECT *
FROM `ansible`.`tasks`
ORDER BY event_date DESC
LIMIT 10


┌─event_date─┬──playbook──┬─user───┬─role──────────────┬─task─────────────────────────────────────────────────────────────────┬─duration─┐
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - prepare environment                                       │      122 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - update rules                                              │       61 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - generate firewall rules                                   │    14840 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - set environment zone                                      │       45 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - check is environment has publicity                        │       27 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - stopping services                                         │      297 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - sysctl configure                                          │      391 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - ensure loaded kernel modules                              │     1185 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ firewall - create shell helpers                                      │      487 │
│ 2021-11-14 │ bootstrap  │ akimrx │ security/firewall │ gather facts                                                         │     3189 │
└────────────┴────────────┴────────┴───────────────────┴──────────────────────────────────────────────────────────────────────┴──────────┘

10 rows in set. Elapsed: 0.003 sec.
```