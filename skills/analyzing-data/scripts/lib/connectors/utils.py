"""Utility functions for connectors."""

import os
import re
from typing import Any


def substitute_env_vars(value: Any) -> tuple[Any, str | None]:
    """Substitute ${VAR_NAME} with environment variable value."""
    if not isinstance(value, str):
        return value, None
    match = re.match(r"^\$\{([^}]+)\}$", value)
    if match:
        env_var_name = match.group(1)
        env_value = os.environ.get(env_var_name)
        return (env_value if env_value else value), env_var_name
    return value, None
