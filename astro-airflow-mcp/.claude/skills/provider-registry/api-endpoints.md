# Registry API Endpoints

Base URL: `https://airflow.apache.org/registry` (override with `--registry-url` or `AF_REGISTRY_URL`)

## Endpoints

| Endpoint | CLI command | Description |
|---|---|---|
| `/api/providers.json` | `af registry providers` | All providers |
| `/api/providers/{id}/modules.json` | `af registry modules {id}` | Modules (latest version) |
| `/api/providers/{id}/{ver}/modules.json` | `af registry modules {id} -v {ver}` | Modules (pinned version) |
| `/api/providers/{id}/parameters.json` | `af registry parameters {id}` | Constructor params (latest) |
| `/api/providers/{id}/{ver}/parameters.json` | `af registry parameters {id} -v {ver}` | Constructor params (pinned) |
| `/api/providers/{id}/connections.json` | `af registry connections {id}` | Connection types (latest) |
| `/api/providers/{id}/{ver}/connections.json` | `af registry connections {id} -v {ver}` | Connection types (pinned) |

## Response Shapes

### providers.json

```json
{
  "providers": [
    {"id": "amazon", "name": "Amazon", "version": "9.22.0", "lifecycle": "production", "description": "..."}
  ]
}
```

### modules.json

```json
{
  "provider_id": "amazon",
  "provider_name": "Amazon",
  "version": "9.22.0",
  "modules": [
    {
      "id": "amazon-s3-S3Hook",
      "name": "S3Hook",
      "type": "hook",
      "import_path": "airflow.providers.amazon.aws.hooks.s3.S3Hook",
      "module_path": "airflow.providers.amazon.aws.hooks.s3",
      "short_description": "Interact with Amazon S3.",
      "docs_url": "https://airflow.apache.org/docs/...",
      "source_url": "https://github.com/apache/airflow/blob/...",
      "category": "amazon-web-services",
      "provider_id": "amazon",
      "provider_name": "Amazon"
    }
  ]
}
```

Module types: `operator`, `hook`, `sensor`, `transfer`

### parameters.json

```json
{
  "provider_id": "ftp",
  "classes": {
    "airflow.providers.ftp.hooks.ftp.FTPHook": {
      "name": "FTPHook",
      "type": "hook",
      "mro": ["FTPHook", "BaseHook"],
      "parameters": [
        {"name": "ftp_conn_id", "type": "str", "default": "ftp_default"}
      ]
    }
  }
}
```

### connections.json

```json
{
  "provider_id": "amazon",
  "connection_types": [
    {
      "connection_type": "aws",
      "hook_class": "airflow.providers.amazon.aws.hooks.base_aws.AwsBaseHook",
      "standard_fields": ["login", "password"],
      "custom_fields": [{"name": "region_name", "type": "str"}]
    }
  ]
}
```
