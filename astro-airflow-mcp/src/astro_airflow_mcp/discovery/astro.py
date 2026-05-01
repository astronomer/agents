"""Astro discovery backend for discovering deployments via Astro CLI.

Emits ``DiscoveredInstance``s with ``auth_kind="astro_pat"``: af resolves
the user's ``astro login`` session at request time from
``~/.astro/config.yaml``.
"""

from __future__ import annotations

import re
from typing import Any

from astro_airflow_mcp.discovery.astro_cli import (
    AstroCli,
    AstroCliError,
    AstroCliNotAuthenticatedError,
    AstroDeployment,
)
from astro_airflow_mcp.discovery.base import DiscoveredInstance, DiscoveryError
from astro_airflow_mcp.logging import get_logger

logger = get_logger(__name__)


class AstroDiscoveryError(DiscoveryError):
    """Error during Astro discovery."""


class AstroNotAuthenticatedError(AstroDiscoveryError):
    """Raised when user is not authenticated with Astro CLI."""


def _generate_instance_name(deployment: AstroDeployment) -> str:
    """Generate an instance name from deployment info.

    Format: {workspace}-{deployment-name}, lowercase with hyphens.
    """
    workspace = re.sub(r"[^a-zA-Z0-9]+", "-", deployment.workspace_name.lower()).strip("-")
    name = re.sub(r"[^a-zA-Z0-9]+", "-", deployment.name.lower()).strip("-")
    return name if not workspace else f"{workspace}-{name}"


class AstroDiscoveryBackend:
    """Discovery backend for Astro deployments.

    Discovers deployments via the Astro CLI and emits instances configured
    for ``astro_pat`` auth (no per-deployment token minting).
    """

    def __init__(self, cli: AstroCli | None = None) -> None:
        self._cli = cli or AstroCli()

    @property
    def name(self) -> str:
        """The backend name."""
        return "astro"

    def is_available(self) -> bool:
        """Check if the Astro CLI is installed."""
        return self._cli.is_installed()

    def get_context(self) -> str | None:
        """Get the current Astro context (domain), or None if unavailable."""
        return self._cli.get_context()

    def discover(self, all_workspaces: bool = False) -> list[DiscoveredInstance]:
        """Discover Astro deployments.

        Args:
            all_workspaces: If True, discover from all accessible workspaces.

        Raises:
            AstroNotAuthenticatedError: If not authenticated with Astro.
            AstroDiscoveryError: If discovery fails.
        """
        deployments_data = self._list_deployments(all_workspaces)
        if not deployments_data:
            return []

        # Build workspace name -> ID mapping if discovering across workspaces
        workspace_map: dict[str, str] = {}
        if all_workspaces:
            workspace_map = self._get_workspace_map()

        # Always pin to the active context at discover time. If the user
        # later runs `astro context switch dev` and we leave context=None,
        # a recorded astronomer.io deployment URL would receive a
        # dev-tenant bearer (best case 401, worst case credential leak
        # across tenants). Correctness wins over the "follow active
        # context" mental model.
        context = self.get_context()

        instances: list[DiscoveredInstance] = []
        for dep_data in deployments_data:
            instance = self._deployment_to_instance(dep_data, workspace_map, context)
            if instance:
                instances.append(instance)
        return instances

    def _list_deployments(self, all_workspaces: bool) -> list[dict[str, Any]]:
        """List deployments from Astro CLI."""
        try:
            return self._cli.list_deployments(all_workspaces=all_workspaces)
        except AstroCliNotAuthenticatedError as e:
            raise AstroNotAuthenticatedError(
                "Not authenticated with Astro. Run 'astro login' first."
            ) from e
        except AstroCliError as e:
            raise AstroDiscoveryError(f"Failed to list deployments: {e}") from e

    def _get_workspace_map(self) -> dict[str, str]:
        """Get a mapping of workspace name to workspace ID."""
        try:
            workspaces = self._cli.list_workspaces()
            return {ws.get("name", ""): ws.get("id", "") for ws in workspaces}
        except AstroCliError:
            return {}

    def _deployment_to_instance(
        self,
        dep_data: dict[str, Any],
        workspace_map: dict[str, str] | None,
        context: str | None,
    ) -> DiscoveredInstance | None:
        """Convert deployment data to a DiscoveredInstance with PAT auth."""
        dep_id = dep_data.get("deployment_id", "")
        if not dep_id:
            return None

        workspace_id = None
        if workspace_map:
            workspace_name = dep_data.get("workspace", "")
            workspace_id = workspace_map.get(workspace_name)

        try:
            deployment = self._cli.inspect_deployment(dep_id, workspace_id=workspace_id)
        except AstroCliError:
            return None

        return DiscoveredInstance(
            name=_generate_instance_name(deployment),
            url=deployment.airflow_api_url,
            source=self.name,
            auth_kind="astro_pat",
            astro_context=context,
            metadata={
                "deployment_id": deployment.id,
                "workspace_id": deployment.workspace_id,
                "workspace_name": deployment.workspace_name,
                "status": deployment.status,
                "airflow_version": deployment.airflow_version,
                "release_name": deployment.release_name,
            },
        )
