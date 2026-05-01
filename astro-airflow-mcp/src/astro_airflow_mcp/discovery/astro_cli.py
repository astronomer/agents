"""Astro CLI wrapper for auto-discovering deployments."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 - subprocess is needed for CLI wrapper
from dataclasses import dataclass
from pathlib import Path

import yaml


class AstroCliError(Exception):
    """Base exception for Astro CLI errors."""


class AstroCliNotInstalledError(AstroCliError):
    """Raised when the Astro CLI is not installed."""


class AstroCliNotAuthenticatedError(AstroCliError):
    """Raised when the user is not authenticated with Astro CLI."""


@dataclass
class AstroDeployment:
    """Information about an Astro deployment."""

    id: str
    name: str
    workspace_id: str
    workspace_name: str
    airflow_api_url: str
    status: str
    airflow_version: str | None = None
    release_name: str | None = None

    @classmethod
    def from_inspect_yaml(cls, data: dict) -> AstroDeployment:
        """Create from astro deployment inspect YAML output."""
        deployment = data.get("deployment", data)
        config = deployment.get("configuration", {})
        metadata = deployment.get("metadata", {})

        # Get the webserver URL (base URL without /api/v2 suffix)
        # The adapter will add the appropriate API path
        webserver_url = metadata.get("webserver_url", "")
        if webserver_url and not webserver_url.startswith("http"):
            webserver_url = f"https://{webserver_url}"

        return cls(
            id=metadata.get("deployment_id", ""),
            name=config.get("name", ""),
            workspace_id=metadata.get("workspace_id", ""),
            workspace_name=config.get("workspace_name", ""),
            airflow_api_url=webserver_url,
            status=metadata.get("status", "UNKNOWN"),
            airflow_version=metadata.get("airflow_version"),
            release_name=metadata.get("release_name"),
        )


class AstroCli:
    """Wrapper for the Astro CLI."""

    # Keywords in stderr that indicate authentication issues
    # These match the actual error message from `astro` CLI when not logged in
    AUTH_ERROR_KEYWORDS = frozenset(
        [
            "no context set",
            "astro login",
        ]
    )

    def __init__(self) -> None:
        """Initialize the Astro CLI wrapper."""
        self._astro_path: str | None = None

    def _get_astro_path(self) -> str:
        """Get the path to the astro CLI executable."""
        if self._astro_path is None:
            self._astro_path = shutil.which("astro")
            if self._astro_path is None:
                raise AstroCliNotInstalledError(
                    "Astro CLI is not installed. Install it with: brew install astro"
                )
        return self._astro_path

    def _run_command(
        self, args: list[str], timeout: int = 30, check_auth: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Run an astro CLI command.

        Args:
            args: Command arguments (without 'astro' prefix)
            timeout: Timeout in seconds
            check_auth: Whether to check for authentication errors

        Returns:
            CompletedProcess with stdout/stderr

        Raises:
            AstroCliNotInstalledError: If astro CLI is not found
            AstroCliNotAuthenticatedError: If user is not authenticated
            AstroCliError: For other CLI errors
        """
        astro_path = self._get_astro_path()

        result = subprocess.run(  # nosec B603 - astro CLI path is validated via shutil.which
            [astro_path, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        # Check for authentication errors in stderr
        if check_auth and result.returncode != 0:
            stderr_lower = result.stderr.lower()
            if any(keyword in stderr_lower for keyword in self.AUTH_ERROR_KEYWORDS):
                raise AstroCliNotAuthenticatedError(
                    "Not authenticated with Astro. Run 'astro login' first."
                )

        return result

    def _run_list_command(self, args: list[str], entity: str, timeout: int = 30) -> list[dict]:
        """Run a list command and parse table output.

        Args:
            args: Command arguments (without 'astro' prefix)
            entity: Name of the entity being listed (for error messages)
            timeout: Timeout in seconds

        Returns:
            List of dicts with column headers as keys

        Raises:
            AstroCliError: If the command fails
        """
        result = self._run_command(args, timeout=timeout)
        if result.returncode != 0:
            raise AstroCliError(f"Failed to list {entity}: {result.stderr}")
        return self._parse_table_output(result.stdout)

    def _find_column_boundaries(self, header_line: str) -> list[int]:
        """Find column start positions by detecting 2+ space separators.

        Returns:
            List of column start positions (character indices)
        """
        boundaries: list[int] = []
        # Find the start of each column (non-space after 2+ spaces, or start of line)
        in_space_run = True  # Treat start of line as after spaces
        space_count = 0

        for i, char in enumerate(header_line):
            if char == " ":
                space_count += 1
                in_space_run = True
            else:
                # Non-space character
                if in_space_run and (space_count >= 2 or i == 0 or not boundaries):
                    boundaries.append(i)
                in_space_run = False
                space_count = 0

        return boundaries

    def _parse_table_output(self, output: str) -> list[dict]:
        """Parse table output from astro CLI commands.

        The CLI outputs space-aligned tables like:
         NAME     NAMESPACE     DEPLOYMENT ID     ...
         test     foo-1234      abc123            ...

        Uses column boundaries detected by 2+ space separators.
        This handles multi-word headers and varying column widths.

        Args:
            output: Raw stdout from CLI command

        Returns:
            List of dicts with column headers as keys
        """
        lines = output.strip().split("\n")
        if len(lines) < 2:
            return []

        header_line = lines[0]
        boundaries = self._find_column_boundaries(header_line)

        if not boundaries:
            return []

        # Extract header names using boundaries
        headers: list[tuple[str, int]] = []
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else len(header_line)
            header_name = header_line[start:end].strip().lower().replace(" ", "_")
            if header_name:
                headers.append((header_name, start))

        if not headers:
            return []

        # Parse data rows using same boundaries
        results = []
        for line in lines[1:]:
            if not line.strip():
                continue

            row = {}
            for i, (header_name, start_pos) in enumerate(headers):
                # End position is start of next column or end of line
                end_pos = headers[i + 1][1] if i + 1 < len(headers) else len(line)
                # Handle lines shorter than expected
                value = line[start_pos:end_pos].strip() if start_pos < len(line) else ""
                row[header_name] = value

            if any(row.values()):  # Skip empty rows
                results.append(row)

        return results

    def is_installed(self) -> bool:
        """Check if the Astro CLI is installed."""
        try:
            self._get_astro_path()
            return True
        except AstroCliNotInstalledError:
            return False

    def get_context(self) -> str | None:
        """Get the current Astro context (domain).

        Reads ``~/.astro/config.yaml`` directly — that's the source of
        truth that astro CLI itself uses. Falls back to parsing
        ``astro context list`` output if the file isn't readable.

        Returns:
            Context domain (eg ``"astronomer.io"``) or None
        """
        # Primary path: read the active context straight from config.yaml.
        # astro CLI's `context list` colors the active row with ANSI codes
        # rather than marking it with an asterisk, so the table parser is
        # unreliable across CLI versions.
        astro_home = os.environ.get("ASTRO_HOME", str(Path.home() / ".astro"))
        config_path = Path(astro_home) / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path) as f:
                    cfg = yaml.safe_load(f) or {}
                ctx = cfg.get("context")
                if isinstance(ctx, str) and ctx:
                    return ctx
            except (yaml.YAMLError, OSError):
                pass

        # Fallback: parse `astro context list` (legacy asterisk format).
        try:
            result = self._run_command(["context", "list"], check_auth=False)
            if result.returncode != 0:
                return None

            for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                if line.strip().startswith("*"):
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        return parts[1]
            return None
        except (AstroCliError, subprocess.TimeoutExpired):
            return None

    def list_workspaces(self) -> list[dict]:
        """List all accessible workspaces.

        Returns:
            List of workspace dictionaries with 'name' and 'id' keys
        """
        return self._run_list_command(["workspace", "list"], "workspaces")

    def list_deployments(self, all_workspaces: bool = False) -> list[dict]:
        """List deployments.

        Args:
            all_workspaces: If True, list from all accessible workspaces

        Returns:
            List of deployment dictionaries with basic info
        """
        args = ["deployment", "list"]
        if all_workspaces:
            args.append("--all")

        return self._run_list_command(args, "deployments", timeout=60)

    def inspect_deployment(
        self, deployment_id: str, workspace_id: str | None = None
    ) -> AstroDeployment:
        """Get detailed information about a deployment.

        Args:
            deployment_id: Deployment ID (not name)
            workspace_id: Optional workspace ID (needed if not in current workspace)

        Returns:
            AstroDeployment with full details including API URL
        """
        args = ["deployment", "inspect", deployment_id]
        if workspace_id:
            args.extend(["--workspace-id", workspace_id])

        result = self._run_command(args, timeout=30)

        if result.returncode != 0:
            raise AstroCliError(f"Failed to inspect deployment '{deployment_id}': {result.stderr}")

        try:
            data = yaml.safe_load(result.stdout)
            return AstroDeployment.from_inspect_yaml(data)
        except yaml.YAMLError as e:
            raise AstroCliError(f"Failed to parse deployment info: {e}") from e
