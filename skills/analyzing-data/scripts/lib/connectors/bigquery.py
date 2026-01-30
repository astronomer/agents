"""BigQuery connector using google-cloud-bigquery."""

from dataclasses import dataclass, field
from typing import Any

from . import register_connector
from .base import DatabaseConnector


@register_connector
@dataclass
class BigQueryConnector(DatabaseConnector):
    project: str = ""
    credentials_path: str = ""
    location: str = ""
    databases: list[str] = field(default_factory=list)

    @classmethod
    def connector_type(cls) -> str:
        return "bigquery"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BigQueryConnector":
        from .utils import substitute_env_vars

        project, _ = substitute_env_vars(data.get("project", ""))
        credentials_path, _ = substitute_env_vars(data.get("credentials_path", ""))

        return cls(
            project=project,
            credentials_path=credentials_path,
            location=data.get("location", ""),
            databases=data.get("databases", [project] if project else []),
        )

    def validate(self, name: str) -> None:
        if not self.project or self.project.startswith("${"):
            raise ValueError(f"warehouse '{name}': project required for bigquery")

    def get_required_packages(self) -> list[str]:
        return ["google-cloud-bigquery[pandas,pyarrow]", "db-dtypes"]

    def get_env_vars_for_kernel(self) -> dict[str, str]:
        env_vars = {}
        if self.credentials_path:
            env_vars["GOOGLE_APPLICATION_CREDENTIALS"] = self.credentials_path
        return env_vars

    def to_python_prelude(self) -> str:
        if self.credentials_path:
            conn_code = f"""from google.oauth2 import service_account
_credentials = service_account.Credentials.from_service_account_file({self.credentials_path!r})
_client = bigquery.Client(project={self.project!r}, credentials=_credentials)"""
        else:
            conn_code = f"_client = bigquery.Client(project={self.project!r})"

        location_arg = f"location={self.location!r}" if self.location else ""
        auth_type = (
            "Service Account"
            if self.credentials_path
            else "Application Default Credentials"
        )

        status_lines = [
            'print("BigQuery client initialized")',
            f'print(f"   Project: {self.project}")',
        ]
        if self.location:
            status_lines.append(f'print(f"   Location: {self.location}")')
        status_lines.append(f'print("   Auth: {auth_type}")')
        status_lines.append(
            'print("\\nAvailable: run_sql(query) -> polars, run_sql_pandas(query) -> pandas")'
        )
        status_code = "\n".join(status_lines)

        return f'''from google.cloud import bigquery
import polars as pl
import pandas as pd
import os

{conn_code}

def run_sql(query: str, limit: int = 100):
    """Execute SQL and return Polars DataFrame."""
    job_config = bigquery.QueryJobConfig({location_arg})
    query_job = _client.query(query, job_config=job_config)
    df = query_job.to_dataframe()
    result = pl.from_pandas(df)
    return result.head(limit) if limit > 0 and len(result) > limit else result


def run_sql_pandas(query: str, limit: int = 100):
    """Execute SQL and return Pandas DataFrame."""
    job_config = bigquery.QueryJobConfig({location_arg})
    query_job = _client.query(query, job_config=job_config)
    df = query_job.to_dataframe()
    return df.head(limit) if limit > 0 and len(df) > limit else df

{status_code}'''
