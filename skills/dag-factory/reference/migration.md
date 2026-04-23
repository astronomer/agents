# dag-factory Migration Notes (pre-1.0 → 1.0)

When working with an existing project on dag-factory <1.0, watch for these breaking changes when upgrading.

## Breaking Changes

| Change | Old | New |
|--------|-----|-----|
| Class access | `from dagfactory import DagFactory` | `from dagfactory import load_yaml_dags` |
| Loader kwarg (dict) | `default_args_config_dict=` | `defaults_config_dict=` |
| Loader kwarg (path) | `default_args_config_path=` | `defaults_config_path=` |
| Schedule key | `schedule_interval: ...` | `schedule: ...` |
| Timeout shortcuts | `dagrun_timeout_sec: 300` | `dagrun_timeout: {__type__: datetime.timedelta, seconds: 300}` |
| Logical keys | `!and`, `!or`, `!join`, `and`, `or` | `__and__`, `__or__`, `__join__` |
| Timetable parsing | `timetable: {callable: ..., params: ...}` | `timetable: {__type__: ..., __args__: [...]}` |
| Provider deps | Auto-installed | Install Airflow providers manually |
| `clean_dags()` | Available on factory class | Removed; use `AIRFLOW__DAG_PROCESSOR__REFRESH_INTERVAL` |
| Tasks/task_groups format | Dict keyed by id | List with `task_id` / `group_name` (dict still works) |
| KPO type casting | Legacy automatic casting of nested k8s objects | Removed; use `__type__` for nested k8s objects |
| Timeout `*_sec` / `*_secs` shortcuts | `dagrun_timeout_sec`, `retry_delay_sec`, etc. | Use real Airflow names with `__type__: datetime.timedelta` |

## Migration Workflow

1. **Update imports** — replace `DagFactory` usages with `load_yaml_dags(globals_dict=globals(), ...)`.
2. **Rename loader kwargs** — `default_args_config_dict` → `defaults_config_dict`; `default_args_config_path` → `defaults_config_path`.
3. **Install providers explicitly** — add `apache-airflow-providers-*` packages your YAML references to `requirements.txt`.
4. **Rename `schedule_interval` → `schedule`** across all DAGs.
5. **Replace timeout shortcuts** — every `*_sec` / `*_secs` field becomes a `__type__: datetime.timedelta` block with the real Airflow name (`dagrun_timeout`, `retry_delay`, `execution_timeout`, ...).
6. **Update logical dataset keys** — rewrite `!and`/`!or`/`and`/`or`/`!join` to `__and__`/`__or__`/`__join__`. Wrap them under `schedule.datasets` (see SKILL.md for the schedule shape).
7. **Update timetable definitions** — switch from `{callable: ..., params: ...}` to `{__type__: ..., __args__: [...]}`.
8. **Convert `tasks` / `task_groups` dicts to lists** (optional but recommended). Each entry needs a `task_id` or `group_name` key.
9. **Remove `clean_dags()` calls** — set `AIRFLOW__DAG_PROCESSOR__REFRESH_INTERVAL` instead.
10. **Convert nested k8s objects** to `__type__: kubernetes.client.models.V1...` blocks.

## Validation After Migration

```bash
# 1. YAML syntax
dagfactory lint dags/

# 2. Airflow 2 → 3 import paths (if also upgrading Airflow)
dagfactory convert dags/ --override

# 3. Have Airflow parse the DAGs
astro dev parse  # or `airflow dags list-import-errors`
```

## Reference

- Official migration guide: https://astronomer.github.io/dag-factory/latest/migration_guide/
