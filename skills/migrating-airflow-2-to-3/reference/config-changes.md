# Configuration File Changes (`airflow.cfg`)

Airflow 3 reorganized many configuration options across sections. These changes affect `airflow.cfg`, environment variables (`AIRFLOW__SECTION__KEY`), and Helm chart overrides.

---

## Options Moved from `[core]` to `[database]`

- `sql_alchemy_conn`
- `sql_engine_encoding`
- `sql_engine_collation_for_ids`
- `sql_alchemy_pool_enabled`
- `sql_alchemy_pool_size`
- `sql_alchemy_max_overflow`
- `sql_alchemy_pool_recycle`
- `sql_alchemy_pool_pre_ping`
- `sql_alchemy_schema`
- `sql_alchemy_connect_args`
- `load_default_connections`
- `max_db_retries`

Example: `AIRFLOW__CORE__SQL_ALCHEMY_CONN` → `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN`

---

## Options Moved from `[core]` to `[logging]`

- `base_log_folder`
- `remote_logging`
- `remote_log_conn_id`
- `remote_base_log_folder`
- `encrypt_s3_logs`
- `logging_level`
- `fab_logging_level`
- `logging_config_class`
- `colored_console_log`
- `colored_log_format`
- `colored_formatter_class`
- `log_format`
- `simple_log_format`
- `task_log_prefix_template`
- `log_filename_template`
- `log_processor_filename_template`
- `dag_processor_manager_log_location`
- `task_log_reader`
- `interleave_timestamp_parser`

Example: `AIRFLOW__CORE__REMOTE_LOGGING` → `AIRFLOW__LOGGING__REMOTE_LOGGING`

---

## Renamed Options

| Old Location | New Location |
|-------------|-------------|
| `[scheduler]deactivate_stale_dags_interval` | `[scheduler]parsing_cleanup_interval` |
| `[scheduler]max_threads` | `[scheduler]parsing_processes` |
| `[scheduler]process_poll_interval` | `[scheduler]scheduler_idle_sleep_time` |
| `[webserver]web_server_host` | `[api]host` |
| `[webserver]session_lifetime_days` | `[webserver]session_lifetime_minutes` |
| `[webserver]force_log_out_after` | `[webserver]session_lifetime_minutes` |
| `[webserver]update_fab_perms` | `[fab]update_fab_perms` |
| `[webserver]auth_rate_limited` | `[fab]auth_rate_limited` |
| `[webserver]auth_rate_limit` | `[fab]auth_rate_limit` |
| `[api]auth_backend` | `[api]auth_backends` |
| `[api]access_control_allow_origin` | `[api]access_control_allow_origins` |
| `[core]dag_concurrency` | `[core]max_active_tasks_per_dag` |

---

## Removed Options

| Option | Notes |
|--------|-------|
| `[webserver]error_logfile` | Removed entirely |
| `[scheduler]dependency_detector` | Removed entirely |
| `[kubernetes]` section | Replaced by `[kubernetes_executor]` |
