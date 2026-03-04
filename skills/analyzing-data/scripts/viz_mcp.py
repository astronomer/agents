#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "fastmcp[apps]>=3.1.0",
#     "prefab-ui==0.10.0",
# ]
# ///
"""Visualization-only MCP server for the analyzing-data skill.

This server is intentionally small:
- Query execution and business logic stay in `scripts/cli.py`
- This server only renders MCP App visualizations (table/chart)
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from prefab_ui.app import PrefabApp
from prefab_ui.components import (
    Column,
    DataTable,
    DataTableColumn,
    Heading,
    Muted,
    Tab,
    Tabs,
)
from prefab_ui.components.charts import BarChart, ChartSeries, LineChart

MAX_ROWS = 500

mcp = FastMCP(
    "Analytics Visualization MCP",
    instructions=(
        "Visualization-only server for query result display. "
        "Use render_table for tabular results and render_chart for line/bar charts. "
        "Do not run SQL here."
    ),
)


def _to_json_safe(value: Any) -> Any:
    """Convert values into JSON-safe types for tool payloads."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    return str(value)


def _normalize_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Normalize rows and enforce a max payload size."""
    if not isinstance(rows, list):
        raise ValueError("rows must be a list of objects")

    normalized: list[dict[str, Any]] = []
    for row in rows[:MAX_ROWS]:
        if not isinstance(row, Mapping):
            raise ValueError("each row must be an object/dict")
        normalized.append(
            {str(key): _to_json_safe(value) for key, value in row.items()}
        )

    return normalized, len(rows) > MAX_ROWS


def _build_table_app(title: str, rows: list[dict[str, Any]]) -> PrefabApp:
    """Build a Prefab DataTable app."""
    keys = list(dict.fromkeys(k for row in rows for k in row))
    columns = [DataTableColumn(key=k, header=k, sortable=True) for k in keys]

    with Column(gap=4, css_class="p-6") as view:
        Heading(title)
        Muted(f"{len(rows)} rows")
        DataTable(
            columns=columns,
            rows=rows,
            searchable=True,
            paginated=True,
            page_size=20,
        )

    return PrefabApp(view=view)


def _build_chart_app(
    title: str,
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    chart_type: str,
    top_n: int | None,
    sort_desc: bool,
) -> PrefabApp:
    """Build a Prefab chart app with tabs for chart and table views."""
    if sort_desc:
        rows = sorted(rows, key=lambda r: _numeric(r.get(y_key)), reverse=True)
    else:
        rows = sorted(rows, key=lambda r: _numeric(r.get(y_key)))

    display_rows = rows[:top_n] if top_n and top_n > 0 else rows

    Chart = BarChart if chart_type == "bar" else LineChart
    keys = list(dict.fromkeys(k for row in rows for k in row))
    columns = [DataTableColumn(key=k, header=k, sortable=True) for k in keys]

    with Column(gap=4, css_class="p-6") as view:
        Heading(title)
        Muted(
            f"Showing {len(display_rows)} of {len(rows)} rows · Ask in chat for a different count"
        )
        with Tabs():
            with Tab("Chart"):
                Chart(
                    data=display_rows,
                    series=[ChartSeries(data_key=y_key, label=y_key)],
                    x_axis=x_key,
                    show_legend=True,
                )
            with Tab("Table"):
                DataTable(
                    columns=columns,
                    rows=display_rows,
                    searchable=True,
                    paginated=True,
                    page_size=20,
                )

    return PrefabApp(view=view)


def _numeric(value: Any) -> float:
    """Extract a numeric value for sorting, defaulting to -inf."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").replace("$", ""))
        except ValueError:
            pass
    return float("-inf")


@mcp.tool(app=True)
def render_table(
    rows: list[dict[str, Any]],
    title: str = "Query Results",
) -> ToolResult:
    """Render rows in an interactive table MCP App.

    Args:
        rows: Array of row objects from a query
        title: Table title
    """
    normalized, truncated = _normalize_rows(rows)
    summary = f"{title}: {len(normalized)} rows"
    if truncated:
        summary += f" (truncated from {len(rows)})"
    return ToolResult(
        content=summary,
        structured_content=_build_table_app(title, normalized),
    )


@mcp.tool(app=True)
def render_chart(
    rows: list[dict[str, Any]],
    x_key: str,
    y_key: str,
    chart_type: Literal["bar", "line"] = "line",
    title: str = "Query Chart",
    top_n: int | None = None,
    sort_desc: bool = True,
) -> ToolResult:
    """Render rows as a line/bar chart in an MCP App.

    Args:
        rows: Array of row objects from a query
        x_key: Column to use as labels (x-axis)
        y_key: Column to use as metric values (y-axis)
        chart_type: "line" or "bar"
        title: Chart title
        top_n: Show only top N rows (default: show all)
        sort_desc: Sort by metric descending (default: True)
    """
    normalized, truncated = _normalize_rows(rows)
    available_keys = sorted({key for row in normalized for key in row})

    if x_key not in available_keys:
        raise ValueError(f"x_key '{x_key}' not found. Available keys: {available_keys}")
    if y_key not in available_keys:
        raise ValueError(f"y_key '{y_key}' not found. Available keys: {available_keys}")

    display_count = min(top_n, len(normalized)) if top_n else len(normalized)
    summary = f"{title}: {display_count} of {len(normalized)} rows, {chart_type} chart by {y_key}"
    if truncated:
        summary += f" (truncated from {len(rows)})"

    return ToolResult(
        content=summary,
        structured_content=_build_chart_app(
            title=title,
            rows=normalized,
            x_key=x_key,
            y_key=y_key,
            chart_type=chart_type,
            top_n=top_n,
            sort_desc=sort_desc,
        ),
    )


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="stdio")
