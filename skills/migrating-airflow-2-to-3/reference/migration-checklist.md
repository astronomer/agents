<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**  *generated with [DocToc](https://github.com/thlorenz/doctoc)*

- [Migration Checklist](#migration-checklist)
  - [1. Direct metadata DB access](#1-direct-metadata-db-access)
  - [2. Legacy imports](#2-legacy-imports)
  - [3. Removed DAG arguments](#3-removed-dag-arguments)
  - [4. Deprecated context keys](#4-deprecated-context-keys)
  - [5. XCom pickling](#5-xcom-pickling)
  - [6. Datasets to Assets](#6-datasets-to-assets)
  - [7. Removed operators](#7-removed-operators)
  - [8. Email changes](#8-email-changes)
  - [9. REST API v1](#9-rest-api-v1)
  - [10. File paths](#10-file-paths)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Migration Checklist

After running Ruff's AIR rules, use this manual search checklist to find remaining issues.

## 1. Direct metadata DB access

**Search for:**
- `provide_session`
- `create_session`
- `Session(`
- `engine`

**Fix:** Refactor to use Airflow Python client or REST API

---

## 2. Legacy imports

**Search for:**
- `from airflow.contrib`
- `from airflow.operators.`
- `from airflow.hooks.`

**Fix:** Map to provider imports (see [migration-patterns.md](migration-patterns.md))

---

## 3. Removed DAG arguments

**Search for:**
- `schedule_interval=`
- `timetable=`
- `days_ago(`
- `fail_stop=`

**Fix:** Use `schedule=` and `pendulum`

---

## 4. Deprecated context keys

**Search for:**
- `execution_date`
- `prev_ds`
- `next_ds`
- `yesterday_ds`
- `tomorrow_ds`

**Fix:** Use `data_interval_start/end` and `dag_run.logical_date`

---

## 5. XCom pickling

**Search for:**
- `ENABLE_XCOM_PICKLING`
- `.xcom_pull(` without `task_ids=`

**Fix:** Use JSON-serializable data or custom backend

---

## 6. Datasets to Assets

**Search for:**
- `airflow.datasets`
- `triggering_dataset_events`

**Fix:** Switch to `airflow.sdk.Asset`

---

## 7. Removed operators

**Search for:**
- `SubDagOperator`
- `SimpleHttpOperator`
- `DagParam`
- `DummyOperator`

**Fix:** Use TaskGroups, HttpOperator, Param, EmptyOperator

---

## 8. Email changes

**Search for:**
- `airflow.operators.email.EmailOperator`

**Fix:** Use SMTP provider

---

## 9. REST API v1

**Search for:**
- `/api/v1`

**Fix:** Update to `/api/v2` with Bearer tokens

---

## 10. File paths

**Search for:**
- `open("include/...)`
- relative paths

**Fix:** Use `__file__` or `AIRFLOW_HOME` anchoring
