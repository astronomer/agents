"""Pydantic models for af CLI configuration."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Auth(BaseModel):
    """Authentication configuration for an Airflow instance."""

    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, description="Username for basic auth")
    password: str | None = Field(default=None, description="Password for basic auth")
    token: str | None = Field(default=None, description="Bearer token for token auth")

    @model_validator(mode="after")
    def validate_auth_method(self) -> Auth:
        """Ensure auth has either basic auth or token auth configured."""
        has_basic = self.username is not None and self.password is not None
        has_token = self.token is not None

        if not has_basic and not has_token:
            raise ValueError("Auth must have either username/password or token configured")
        if has_basic and has_token:
            raise ValueError("Auth cannot have both username/password and token configured")

        return self


class Instance(BaseModel):
    """An Airflow instance with its URL and authentication."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Unique name for this instance")
    url: str = Field(..., description="Base URL of the Airflow webserver")
    auth: Auth | None = Field(default=None, description="Authentication configuration (optional)")


class AirflowCliConfig(BaseModel):
    """Root configuration model for af CLI."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    instances: Annotated[list[Instance], Field(default_factory=list)]
    current_instance: Annotated[str | None, Field(default=None, alias="current-instance")]

    def get_instance(self, name: str) -> Instance | None:
        """Get an instance by name."""
        for instance in self.instances:
            if instance.name == name:
                return instance
        return None

    @model_validator(mode="after")
    def validate_references(self) -> AirflowCliConfig:
        """Validate that current-instance references an existing instance."""
        if self.current_instance is not None:
            instance_names = {i.name for i in self.instances}
            if self.current_instance not in instance_names:
                raise ValueError(f"current-instance '{self.current_instance}' does not exist")
        return self

    def add_instance(
        self,
        name: str,
        url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
    ) -> None:
        """Add or update an instance."""
        # Only create Auth if credentials provided
        has_basic = username is not None and password is not None
        has_token = token is not None
        auth = (
            Auth(username=username, password=password, token=token)
            if has_basic or has_token
            else None
        )

        existing = self.get_instance(name)
        if existing:
            # Update existing instance
            idx = self.instances.index(existing)
            self.instances[idx] = Instance(name=name, url=url, auth=auth)
        else:
            self.instances.append(Instance(name=name, url=url, auth=auth))

    def delete_instance(self, name: str) -> None:
        """Delete an instance by name."""
        instance = self.get_instance(name)
        if not instance:
            raise ValueError(f"Instance '{name}' does not exist")

        self.instances.remove(instance)

        if self.current_instance == name:
            self.current_instance = None

    def use_instance(self, name: str) -> None:
        """Set the current instance."""
        if not self.get_instance(name):
            raise ValueError(f"Instance '{name}' does not exist")
        self.current_instance = name
