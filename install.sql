CREATE DATABASE IF NOT EXISTS `ansible`;

CREATE TABLE IF NOT EXISTS `ansible`.`logs`(
    `event_date` Date COMMENT 'playbook launch date',
    `start_time` DateTime COMMENT 'playbook launch time',
    `end_time` DateTime COMMENT 'playbook completion time',
    `duration` UInt32 COMMENT 'the total duration of the playbook in seconds',
    `user` LowCardinality(String) COMMENT 'the user who launched the playbook',
    `hostname` String COMMENT 'the hostname from which the playbook is launched',
    `inventory` LowCardinality(String) COMMENT 'inventory name',
    `playbook` LowCardinality(String) COMMENT 'playbook name',
    `event_type` LowCardinality(String) COMMENT 'playbook launch type: check or play',
    `status` LowCardinality(String) COMMENT 'playbook execution status',
    `branch` String COMMENT 'git branch name',
    `tags` Array(String) COMMENT 'tags passed in the launch',
    `skipped_tags` Array(String) COMMENT 'tags skipped in the launch',
    `extra_vars` Array(String) COMMENT 'extra vars passed in the launch',
    `limit_expression` String COMMENT 'passed limit argument',
    `hosts` Array(String) COMMENT 'array of target servers or groups to which the changes are applied',
    `affected_hosts_count` UInt16 COMMENT 'number of affected servers within the playbook',
    `unreachable_hosts_count` UInt16 COMMENT 'number of servers unavailable to the user',
    `failed_hosts_count` UInt16 COMMENT 'the number of servers on which the playbook failed with an error',
    `connection_mode` LowCardinality(String) COMMENT 'ansible connection mode',
    `forks_count` UInt8 COMMENT 'number of forks for the playbook',
    `pure_play` UInt8 DEFAULT 0 COMMENT 'flag that defines the execution of the playbook from scratch'
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (
    event_date,
    end_time,
    event_type,
    inventory,
    playbook
);

CREATE TABLE IF NOT EXISTS `ansible`.`tasks`(
    `event_date` Date COMMENT 'task launch date',
    `playbook` LowCardinality(String) COMMENT 'playbook name',
    `user` LowCardinality(String) COMMENT 'the user who launched the playbook',
    `role` String COMMENT 'role name',
    `task` String COMMENT 'task fullname',
    `duration` Decimal32 COMMENT 'total duration of task execution in milliseconds',

)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_date)
ORDER BY (
    event_date,
    playbook,
    role
);
