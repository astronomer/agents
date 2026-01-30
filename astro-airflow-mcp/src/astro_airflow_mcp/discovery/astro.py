"""Astro discovery backend for discovering deployments via Astro CLI."""

from __future__ import annotations

import re
from typing import Any

from astro_airflow_mcp.astro.astro_cli import (
    AstroCli,
    AstroCliError,
    AstroCliNotAuthenticatedError,
    AstroDeployment,
)
from astro_airflow_mcp.discovery.base import DiscoveredInstance, DiscoveryError


class AstroDiscoveryError(DiscoveryError):
    """Error during Astro discovery."""


class AstroNotAuthenticatedError(AstroDiscoveryError):
    """Raised when user is not authenticated with Astro CLI."""


def _generate_instance_name(deployment: AstroDeployment) -> str:
    """Generate an instance name from deployment info.

    Format: {workspace}-{deployment-name}
    Normalizes to lowercase with hyphens.

    Args:
        deployment: The Astro deployment

    Returns:
        A normalized instance name
    """
    # Normalize workspace and deployment names
    workspace = re.sub(r"[^a-zA-Z0-9]+", "-", deployment.workspace_name.lower()).strip("-")
    name = re.sub(r"[^a-zA-Z0-9]+", "-", deployment.name.lower()).strip("-")

    # Handle empty workspace name
    return name if not workspace else f"{workspace}-{name}"


class AstroDiscoveryBackend:
    """Discovery backend for Astro deployments.

    Uses the Astro CLI to discover deployments and optionally create
    deployment tokens for authentication.
    """

    def __init__(self, cli: AstroCli | None = None) -> None:
        """Initialize the Astro discovery backend.

        Args:
            cli: Optional AstroCli instance (creates one if not provided)
        """
        self._cli = cli or AstroCli()

    @property
    def name(self) -> str:
        """The backend name."""
        return "astro"

    def is_available(self) -> bool:
        """Check if the Astro CLI is installed."""
        return self._cli.is_installed()

    def get_context(self) -> str | None:
        """Get the current Astro context (domain).

        Returns:
            Context domain or None if not available
        """
        return self._cli.get_context()

    def discover(
        self,
        all_workspaces: bool = False,
        create_tokens: bool = True,
        **kwargs: Any,
    ) -> list[DiscoveredInstance]:
        """Discover Astro deployments.

        Args:
            all_workspaces: If True, discover from all accessible workspaces
            create_tokens: If True, create deployment tokens (default: True)
            **kwargs: Additional options (ignored)

        Returns:
            List of discovered instances

        Raises:
            AstroNotAuthenticatedError: If not authenticated with Astro
            AstroDiscoveryError: If discovery fails
        """
        # List deployments
        try:
            deployments_data = self._cli.list_deployments(all_workspaces=all_workspaces)
        except AstroCliNotAuthenticatedError as e:
            raise AstroNotAuthenticatedError(
                "Not authenticated with Astro. Run 'astro login' first."
            ) from e
        except AstroCliError as e:
            raise AstroDiscoveryError(f"Failed to list deployments: {e}") from e

        if not deployments_data:
            return []

        # Inspect each deployment to get full details
        instances: list[DiscoveredInstance] = []
        for dep_data in deployments_data:
            dep_id = dep_data.get("deployment_id", "")

            if not dep_id:
                continue

            try:
                deployment = self._cli.inspect_deployment(dep_id)
            except AstroCliError:
                continue

            instance_name = _generate_instance_name(deployment)

            # Optionally create token
            token: str | None = None
            if create_tokens:
                token = self._get_or_create_token(deployment)

            instances.append(
                DiscoveredInstance(
                    name=instance_name,
                    url=deployment.airflow_api_url,
                    source=self.name,
                    auth_token=token,
                    metadata={
                        "deployment_id": deployment.id,
                        "workspace_id": deployment.workspace_id,
                        "workspace_name": deployment.workspace_name,
                        "status": deployment.status,
                        "airflow_version": deployment.airflow_version,
                        "release_name": deployment.release_name,
                    },
                )
            )

        return instances

    def _get_or_create_token(self, deployment: AstroDeployment) -> str | None:
        """Get existing token or create a new one.

        Args:
            deployment: The deployment to get/create token for

        Returns:
            Token value or None if token already exists and can't be retrieved
        """
        try:
            # Check if token already exists
            if self._cli.token_exists(deployment.id, AstroCli.TOKEN_NAME):
                # Can't retrieve existing token value
                return None

            # Create new token
            return self._cli.create_deployment_token(deployment.id, AstroCli.TOKEN_NAME)
        except AstroCliError:
            return None

    def token_exists(self, deployment_id: str) -> bool:
        """Check if the discovery token already exists for a deployment.

        Args:
            deployment_id: The deployment ID

        Returns:
            True if token exists
        """
        try:
            return self._cli.token_exists(deployment_id, AstroCli.TOKEN_NAME)
        except AstroCliError:
            return False

    def create_token(self, deployment_id: str) -> str:
        """Create a new deployment token.

        Args:
            deployment_id: The deployment ID

        Returns:
            The token value

        Raises:
            AstroDiscoveryError: If token creation fails
        """
        try:
            return self._cli.create_deployment_token(deployment_id, AstroCli.TOKEN_NAME)
        except AstroCliError as e:
            raise AstroDiscoveryError(f"Failed to create token: {e}") from e
