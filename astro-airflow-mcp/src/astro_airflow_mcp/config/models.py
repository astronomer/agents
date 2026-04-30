"""Pydantic models for af CLI configuration."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Sentinel used by the discovery flow to add a PAT-backed instance even
# though Auth() requires _some_ credential field by default. The kind
# discriminator lets `astro_pat` short-circuit the basic/token validation.
AuthKind = Literal["basic", "token", "astro_pat"]


class Auth(BaseModel):
    """Authentication configuration for an Airflow instance.

    Three kinds:
      - ``basic``: username + password
      - ``token``: a static bearer (env-var interpolation supported)
      - ``astro_pat``: reuse the user's ``astro login`` session (default for
        Astro-source instances). Stores no credential on disk; resolved at
        request time from ``~/.astro/config.yaml``.

    For backward compatibility, ``kind`` is inferred when missing: if
    ``token`` is set we treat it as ``token``; if ``username``/``password``
    are set we treat it as ``basic``. Configs written before this field
    existed continue to load without modification.
    """

    model_config = ConfigDict(extra="forbid")

    kind: AuthKind | None = Field(
        default=None,
        description=(
            "Auth kind. Inferred from other fields when omitted: "
            "token→'token', username/password→'basic'."
        ),
    )
    username: str | None = Field(default=None, description="Username for basic auth")
    password: str | None = Field(default=None, description="Password for basic auth")
    token: str | None = Field(default=None, description="Bearer token for token auth")
    context: str | None = Field(
        default=None,
        description=(
            "Astro context (eg 'astronomer.io') for astro_pat auth. "
            "Used to look up the right credential in ~/.astro/config.yaml."
        ),
    )
    deployment_id: str | None = Field(
        default=None,
        description=("Astro deployment ID. Recorded for diagnostics; not used for auth itself."),
    )

    @model_validator(mode="after")
    def validate_auth_method(self) -> Auth:
        """Validate the auth shape and infer kind if absent."""
        # Infer kind from fields if not set.
        if self.kind is None:
            if self.token is not None:
                self.kind = "token"
            elif self.username is not None or self.password is not None:
                self.kind = "basic"
            elif self.context is not None:
                # `context` set without kind is a config the user wrote by
                # hand expecting astro_pat — be permissive.
                self.kind = "astro_pat"
            else:
                raise ValueError(
                    "Auth must have one of: token, username/password, or "
                    "kind=astro_pat with context"
                )

        if self.kind == "basic":
            if self.username is None or self.password is None:
                raise ValueError("kind=basic requires both username and password")
            if self.token is not None:
                raise ValueError("kind=basic cannot also have a token")
            if self.context is not None:
                raise ValueError("kind=basic cannot have a context")
        elif self.kind == "token":
            if self.token is None:
                raise ValueError("kind=token requires token")
            if self.username is not None or self.password is not None:
                raise ValueError("kind=token cannot also have username/password")
            if self.context is not None:
                raise ValueError("kind=token cannot have a context")
        elif self.kind == "astro_pat":
            if self.username is not None or self.password is not None:
                raise ValueError("kind=astro_pat cannot have username/password")
            if self.token is not None:
                raise ValueError("kind=astro_pat cannot have a token")
            # context is optional — when missing we use the active astro context.

        return self


class Instance(BaseModel):
    """An Airflow instance with its URL and authentication."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(..., description="Unique name for this instance")
    url: str = Field(..., description="Base URL of the Airflow webserver")
    auth: Auth | None = Field(default=None, description="Authentication configuration (optional)")
    source: str | None = Field(
        default=None, description="Discovery source (e.g., astro, local, manual)"
    )
    verify_ssl: Annotated[
        bool,
        Field(default=True, alias="verify-ssl", description="Whether to verify SSL certificates"),
    ]
    ca_cert: Annotated[
        str | None,
        Field(default=None, alias="ca-cert", description="Path to custom CA certificate bundle"),
    ]


class Telemetry(BaseModel):
    """Telemetry configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether anonymous telemetry is enabled")
    anonymous_id: str | None = Field(default=None, description="Anonymous user ID for telemetry")


class AirflowCliConfig(BaseModel):
    """Root configuration model for af CLI."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    instances: Annotated[list[Instance], Field(default_factory=list)]
    current_instance: Annotated[str | None, Field(default=None, alias="current-instance")]
    telemetry: Telemetry = Field(default_factory=Telemetry)

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
        kind: AuthKind | None = None,
        context: str | None = None,
        deployment_id: str | None = None,
        source: str | None = None,
        verify_ssl: bool = True,
        ca_cert: str | None = None,
    ) -> None:
        """Add or update an instance.

        ``kind`` defaults to inference: ``astro_pat`` if context is given,
        else ``token`` if token is given, else ``basic`` if user/pass.
        """
        has_basic = username is not None and password is not None
        has_token = token is not None
        has_pat = kind == "astro_pat" or (kind is None and context is not None)

        if has_basic or has_token or has_pat:
            auth = Auth(
                kind=kind,
                username=username,
                password=password,
                token=token,
                context=context,
                deployment_id=deployment_id,
            )
        else:
            auth = None

        instance = Instance(
            name=name,
            url=url,
            auth=auth,
            source=source,
            verify_ssl=verify_ssl,
            ca_cert=ca_cert,
        )
        existing = self.get_instance(name)
        if existing:
            idx = self.instances.index(existing)
            self.instances[idx] = instance
        else:
            self.instances.append(instance)

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
