"""Environment variable interpolation for config values."""

from __future__ import annotations

import os
import re


def interpolate_env_vars(value: str) -> str:
    """Replace ${VAR} patterns with environment variable values.

    Args:
        value: String that may contain ${VAR} patterns

    Returns:
        String with environment variables expanded

    Raises:
        ValueError: If an environment variable is not set
    """
    pattern = re.compile(r"\$\{([^}]+)\}")

    def replace_var(match: re.Match[str]) -> str:
        var_name = match.group(1)
        env_value = os.environ.get(var_name)
        if env_value is None:
            raise ValueError(f"Environment variable '{var_name}' is not set")
        return env_value

    return pattern.sub(replace_var, value)


def interpolate_config_value(value: str | None) -> str | None:
    """Interpolate environment variables in a config value if present.

    Args:
        value: Optional string that may contain ${VAR} patterns

    Returns:
        Interpolated string or None if input is None
    """
    if value is None:
        return None
    return interpolate_env_vars(value)
