"""Generic API command for direct Airflow REST API access."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer
import yaml

from astro_airflow_mcp.cli.context import get_adapter
from astro_airflow_mcp.cli.output import output_error, output_json


def parse_field_value(value: str) -> Any:
    """Convert string value to appropriate Python type.

    Supports:
    - null -> None
    - true/false -> bool
    - integers and floats
    - @filename -> file contents
    - everything else -> string
    """
    if value == "null":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("@"):
        # Read from file
        filepath = Path(value[1:])
        try:
            return filepath.read_text()
        except FileNotFoundError:
            raise typer.BadParameter(f"File not found: {filepath}") from None
        except PermissionError:
            raise typer.BadParameter(f"Permission denied reading file: {filepath}") from None
        except IsADirectoryError:
            raise typer.BadParameter(f"Path is a directory, not a file: {filepath}") from None
        except OSError as e:
            raise typer.BadParameter(f"Error reading file {filepath}: {e}") from None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def parse_field(field: str, raw: bool = False) -> tuple[str, Any]:
    """Parse a key=value field string.

    Args:
        field: String in format "key=value"
        raw: If True, don't do type conversion (keep as string)

    Returns:
        Tuple of (key, value)
    """
    if "=" not in field:
        raise typer.BadParameter(f"Field must be in key=value format: {field}")

    key, value = field.split("=", 1)
    if raw:
        return key, value
    return key, parse_field_value(value)


def format_output(
    result: dict[str, Any],
    include_headers: bool = False,
) -> None:
    """Format and output the API response.

    Args:
        result: Raw response dict with status_code, headers, body
        include_headers: If True, include status and headers in output
    """
    if include_headers:
        output = {
            "status_code": result["status_code"],
            "headers": result["headers"],
            "body": result["body"],
        }
        output_json(output)
    else:
        # Just output the body
        if result["body"] is not None:
            if isinstance(result["body"], str):
                print(result["body"])
            else:
                output_json(result["body"])


def api_command(
    endpoint: Annotated[
        str | None,
        typer.Argument(
            help="API endpoint path (e.g., 'dags', '/dags/my_dag'). Leading slash optional."
        ),
    ] = None,
    method: Annotated[
        str,
        typer.Option(
            "--method",
            "-X",
            help="HTTP method (GET, POST, PATCH, PUT, DELETE)",
        ),
    ] = "GET",
    field: Annotated[
        list[str] | None,
        typer.Option(
            "--field",
            "-F",
            help="Typed field in key=value format. Auto-converts numbers, booleans, null. Repeatable.",
        ),
    ] = None,
    raw_field: Annotated[
        list[str] | None,
        typer.Option(
            "--raw-field",
            "-f",
            help="Raw string field in key=value format. No type conversion. Repeatable.",
        ),
    ] = None,
    header: Annotated[
        list[str] | None,
        typer.Option(
            "--header",
            "-H",
            help="Custom header in 'key:value' format. Repeatable.",
        ),
    ] = None,
    body: Annotated[
        str | None,
        typer.Option(
            "--body",
            help="JSON request body (alternative to -F/-f fields)",
        ),
    ] = None,
    include: Annotated[
        bool,
        typer.Option(
            "--include",
            "-i",
            help="Include HTTP status code and headers in output",
        ),
    ] = False,
    raw: Annotated[
        bool,
        typer.Option(
            "--raw",
            help="Use endpoint path as-is without API version prefix",
        ),
    ] = False,
    spec: Annotated[
        bool,
        typer.Option(
            "--spec",
            help="Fetch full OpenAPI spec (JSON)",
        ),
    ] = False,
    endpoints: Annotated[
        bool,
        typer.Option(
            "--endpoints",
            help="List available API endpoints",
        ),
    ] = False,
    filter_pattern: Annotated[
        str | None,
        typer.Option(
            "--filter",
            help="Filter endpoints containing this string (use with --endpoints)",
        ),
    ] = None,
) -> None:
    """Make direct requests to any Airflow REST API endpoint.

    Similar to `gh api` for GitHub, this command provides direct access
    to the Airflow REST API. The API version prefix (/api/v1 or /api/v2)
    is automatically added based on the Airflow version.

    Examples:

        # List all available endpoints
        af api --endpoints

        # Filter endpoints by pattern
        af api --endpoints --filter variable

        # List DAGs
        af api dags

        # Get specific DAG
        af api dags/my_dag

        # List DAGs with query parameters
        af api dags -F limit=10 -F only_active=true

        # Create a variable
        af api variables -X POST -F key=my_var -f value="my value"

        # Delete a connection
        af api connections/old_conn -X DELETE

        # Include response headers
        af api dags -i

        # Access non-versioned endpoint (like /health)
        af api health --raw

        # Fetch full OpenAPI spec
        af api --spec
    """
    # Handle --spec flag
    if spec:
        try:
            adapter = get_adapter()
            # Try AF3 location first (/openapi.json), then AF2 (/api/v1/openapi.yaml)
            result = adapter.raw_request("GET", "openapi.json", raw_endpoint=True)
            is_yaml = False
            if result["status_code"] == 404:
                # Fall back to AF2 location (YAML format)
                result = adapter.raw_request("GET", "openapi.yaml", raw_endpoint=False)
                is_yaml = True
            if result["status_code"] >= 400:
                output_error(f"HTTP {result['status_code']}: {result.get('body', 'Unknown error')}")
            # Parse YAML if needed
            if is_yaml and isinstance(result["body"], str):
                result["body"] = yaml.safe_load(result["body"])
            format_output(result, include_headers=include)
        except Exception as e:
            output_error(str(e))
        return

    # Handle --endpoints flag
    if endpoints:
        try:
            adapter = get_adapter()
            # Try AF3 location first (/openapi.json), then AF2 (/api/v1/openapi.yaml)
            result = adapter.raw_request("GET", "openapi.json", raw_endpoint=True)
            is_yaml = False
            if result["status_code"] == 404:
                # Fall back to AF2 location (YAML format)
                result = adapter.raw_request("GET", "openapi.yaml", raw_endpoint=False)
                is_yaml = True
            if result["status_code"] >= 400:
                output_error(f"HTTP {result['status_code']}: {result.get('body', 'Unknown error')}")
            # Parse YAML if needed, extract endpoint paths
            spec_data = result["body"]
            if is_yaml and isinstance(spec_data, str):
                spec_data = yaml.safe_load(spec_data)
            if isinstance(spec_data, dict) and "paths" in spec_data:
                paths = sorted(spec_data["paths"].keys())
                if filter_pattern:
                    paths = [p for p in paths if filter_pattern.lower() in p.lower()]
                output_json({"endpoints": paths, "count": len(paths)})
            else:
                output_error("Could not parse OpenAPI spec")
        except Exception as e:
            output_error(str(e))
        return

    # Endpoint is required if not fetching spec or endpoints
    if endpoint is None:
        output_error(
            "Endpoint is required. Use 'af api <endpoint>', 'af api --endpoints', or 'af api --spec'"
        )
        return

    # Validate method
    valid_methods = {"GET", "POST", "PATCH", "PUT", "DELETE"}
    method_upper = method.upper()
    if method_upper not in valid_methods:
        output_error(f"Invalid method '{method}'. Must be one of: {', '.join(valid_methods)}")
        return

    # Parse fields
    fields: dict[str, Any] = {}
    if field:
        for f in field:
            try:
                key, value = parse_field(f, raw=False)
                fields[key] = value
            except typer.BadParameter as e:
                output_error(str(e))
                return
    if raw_field:
        for f in raw_field:
            try:
                key, value = parse_field(f, raw=True)
                fields[key] = value
            except typer.BadParameter as e:
                output_error(str(e))
                return

    # Parse headers
    headers: dict[str, str] = {}
    if header:
        for h in header:
            if ":" not in h:
                output_error(f"Header must be in 'key:value' format: {h}")
                return
            key, value = h.split(":", 1)
            headers[key.strip()] = value.strip()

    # Determine params vs json_data based on method
    params: dict[str, Any] | None = None
    json_data: dict[str, Any] | None = None

    if body:
        # Explicit body takes precedence
        try:
            json_data = json.loads(body)
        except json.JSONDecodeError as e:
            output_error(f"Invalid JSON body: {e}")
            return
    elif fields:
        if method_upper == "GET":
            # For GET, fields become query parameters
            params = fields
        else:
            # For POST/PATCH/PUT/DELETE, fields become JSON body
            json_data = fields

    # Warn about sensitive endpoints that may expose credentials
    endpoint_lower = endpoint.lower()
    if "connection" in endpoint_lower and method_upper == "GET":
        import sys

        print(
            "Warning: Connection endpoints may expose passwords. "
            "Use 'af config connections' for filtered output.",
            file=sys.stderr,
        )

    try:
        adapter = get_adapter()
        result = adapter.raw_request(
            method=method_upper,
            endpoint=endpoint,
            params=params,
            json_data=json_data,
            headers=headers if headers else None,
            raw_endpoint=raw,
        )

        # Check for error status codes
        if result["status_code"] >= 400:
            # Still output the response body for debugging
            format_output(result, include_headers=include)
            raise SystemExit(1)

        format_output(result, include_headers=include)

    except SystemExit:
        raise
    except Exception as e:
        output_error(str(e))
