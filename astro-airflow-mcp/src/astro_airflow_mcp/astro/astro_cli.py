"""Astro CLI wrapper for auto-discovering deployments."""

from __future__ import annotations

import re
import shutil
import subprocess  # nosec B404 - subprocess is needed for CLI wrapper
from dataclasses import dataclass

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

        # Get the API URL directly (add https:// if missing)
        airflow_api_url = metadata.get("airflow_api_url", "")
        if airflow_api_url and not airflow_api_url.startswith("http"):
            airflow_api_url = f"https://{airflow_api_url}"

        return cls(
            id=metadata.get("deployment_id", ""),
            name=config.get("name", ""),
            workspace_id=metadata.get("workspace_id", ""),
            workspace_name=config.get("workspace_name", ""),
            airflow_api_url=airflow_api_url,
            status=metadata.get("status", "UNKNOWN"),
            airflow_version=metadata.get("airflow_version"),
            release_name=metadata.get("release_name"),
        )


class AstroCli:
    """Wrapper for the Astro CLI."""

    # Keywords in stderr that indicate authentication issues
    AUTH_ERROR_KEYWORDS = [
        "please login",
        "not authenticated",
        "have you authenticated",
        "no context set",
        "unauthorized",
        "authentication required",
        "login required",
        "token expired",
        "invalid token",
        "astro login",
    ]

    TOKEN_NAME = "af-cli-discover"  # nosec B105 - not a password, just a token name

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
            for keyword in self.AUTH_ERROR_KEYWORDS:
                if keyword in stderr_lower:
                    raise AstroCliNotAuthenticatedError(
                        "Not authenticated with Astro. Run 'astro login' first."
                    )

        return result

    def _parse_table_output(self, output: str) -> list[dict]:
        """Parse table output from astro CLI commands.

        The CLI outputs space-aligned tables like:
         NAME     NAMESPACE     DEPLOYMENT ID     ...
         test     foo-1234      abc123            ...

        Args:
            output: Raw stdout from CLI command

        Returns:
            List of dicts with column headers as keys
        """
        lines = output.strip().split("\n")
        if len(lines) < 2:
            return []

        # First line is headers - find column positions by looking at where headers start
        header_line = lines[0]

        # Find all column headers and their positions
        # Headers are words/phrases separated by 2+ spaces
        headers: list[tuple[str, int]] = []
        col_pattern = re.compile(r"(\S+(?:\s\S+)*)")

        for match in col_pattern.finditer(header_line):
            header_name = match.group(1).strip().lower().replace(" ", "_")
            headers.append((header_name, match.start()))

        if not headers:
            return []

        # Parse data rows
        results = []
        for line in lines[1:]:
            if not line.strip():
                continue

            row = {}
            for i, (header_name, start_pos) in enumerate(headers):
                # End position is start of next column or end of line
                end_pos = headers[i + 1][1] if i + 1 < len(headers) else len(line)
                value = line[start_pos:end_pos].strip()
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

        Returns:
            Context domain (e.g., 'cloud.astronomer.io') or None
        """
        try:
            result = self._run_command(["context", "list"], check_auth=False)
            if result.returncode != 0:
                return None

            # Parse table output - look for row with asterisk (current context)
            for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                if line.strip().startswith("*"):
                    # Format: * DOMAIN  ...
                    parts = line.strip().split()
                    if len(parts) >= 2:
                        return parts[1]  # Domain is second field after *

            return None
        except (AstroCliError, subprocess.TimeoutExpired):
            return None

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

        result = self._run_command(args, timeout=60)

        if result.returncode != 0:
            raise AstroCliError(f"Failed to list deployments: {result.stderr}")

        return self._parse_table_output(result.stdout)

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

    def list_deployment_tokens(self, deployment_id: str) -> list[dict]:
        """List API tokens for a deployment.

        Args:
            deployment_id: The deployment ID

        Returns:
            List of token dictionaries with id, name, role, etc.
        """
        args = ["deployment", "token", "list", "--deployment-id", deployment_id]

        result = self._run_command(args, timeout=30)

        if result.returncode != 0:
            raise AstroCliError(f"Failed to list deployment tokens: {result.stderr}")

        return self._parse_table_output(result.stdout)

    def token_exists(self, deployment_id: str, token_name: str) -> bool:
        """Check if a token with the given name exists for a deployment.

        Args:
            deployment_id: The deployment ID
            token_name: Name of the token to check

        Returns:
            True if token exists, False otherwise
        """
        tokens = self.list_deployment_tokens(deployment_id)
        return any(t.get("name") == token_name for t in tokens)

    def create_deployment_token(
        self,
        deployment_id: str,
        name: str,
        role: str = "DEPLOYMENT_ADMIN",
        expiry_days: int = 0,
    ) -> str:
        """Create a new deployment API token.

        Args:
            deployment_id: The deployment ID
            name: Name for the token
            role: Token role (DEPLOYMENT_ADMIN, etc.)
            expiry_days: Days until expiration (0 = never)

        Returns:
            The token value (only available at creation time)
        """
        args = [
            "deployment",
            "token",
            "create",
            "--deployment-id",
            deployment_id,
            "--name",
            name,
            "--role",
            role,
        ]

        if expiry_days > 0:
            args.extend(["--expiry", str(expiry_days)])

        result = self._run_command(args, timeout=30)

        if result.returncode != 0:
            raise AstroCliError(f"Failed to create deployment token: {result.stderr}")

        # Token is printed to stdout - extract it
        # Output format may vary, look for JWT-like token
        output = result.stdout.strip()

        # Look for a JWT token pattern (base64.base64.base64)
        jwt_pattern = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
        match = jwt_pattern.search(output)
        if match:
            return match.group(0)

        # If no JWT found, try to find any long alphanumeric string that looks like a token
        # Tokens are typically 100+ characters
        token_pattern = re.compile(r"[A-Za-z0-9_-]{100,}")
        match = token_pattern.search(output)
        if match:
            return match.group(0)

        # Last resort - return the entire output if it looks like a token
        if len(output) > 50 and "\n" not in output:
            return output

        raise AstroCliError(
            f"Token creation succeeded but could not extract token value from output: {output[:200]}"
        )
