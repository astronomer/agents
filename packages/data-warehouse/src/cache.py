"""Persistent cache for schema discovery and query templates.

Cache files are stored at ~/.astro/ai/cache/:
- concepts.json: concept → table mapping (e.g., "customers" → "HQ.MODEL.ORGS")
- tables.json: table → columns, row_count, description
- templates.json: question pattern → query template
- cache_meta.json: TTL settings, validation timestamps
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default TTL for cache entries (7 days)
DEFAULT_TTL_DAYS = 7

# Row count change threshold to trigger re-validation (50%)
ROW_COUNT_CHANGE_THRESHOLD = 0.5


def get_cache_dir() -> Path:
    """Get the cache directory path, creating it if needed."""
    cache_dir = Path.home() / ".astro" / "ai" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _load_json(path: Path) -> dict:
    """Load JSON file, returning empty dict if not found."""
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load cache file {path}: {e}")
    return {}


def _save_json(path: Path, data: dict) -> None:
    """Save data to JSON file."""
    try:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    except OSError as e:
        logger.warning(f"Failed to save cache file {path}: {e}")


@dataclass
class CachedTable:
    """Cached table schema information."""

    database: str
    schema: str
    table_name: str
    columns: list[dict]  # [{name, type, nullable, comment}, ...]
    row_count: int | None = None
    comment: str | None = None
    cached_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_validated: str | None = None

    @property
    def full_name(self) -> str:
        return f"{self.database}.{self.schema}.{self.table_name}"

    def is_stale(self, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
        """Check if cache entry is older than TTL."""
        cached_time = datetime.fromisoformat(self.cached_at)
        return datetime.now() - cached_time > timedelta(days=ttl_days)

    def to_dict(self) -> dict:
        return {
            "database": self.database,
            "schema": self.schema,
            "table_name": self.table_name,
            "columns": self.columns,
            "row_count": self.row_count,
            "comment": self.comment,
            "cached_at": self.cached_at,
            "last_validated": self.last_validated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CachedTable":
        return cls(
            database=data["database"],
            schema=data["schema"],
            table_name=data["table_name"],
            columns=data.get("columns", []),
            row_count=data.get("row_count"),
            comment=data.get("comment"),
            cached_at=data.get("cached_at", datetime.now().isoformat()),
            last_validated=data.get("last_validated"),
        )


@dataclass
class QueryTemplate:
    """A learned query template for a question pattern."""

    pattern_name: str  # e.g., "who_uses_X"
    description: str
    learned_from: str  # Original question that created this template
    fact_table: str  # Main table to query
    template_sql: str  # SQL with {placeholders}
    variables: list[str]  # e.g., ["X"] - what can be substituted
    success_count: int = 1
    last_success: str = field(default_factory=lambda: datetime.now().isoformat())
    avg_runtime_sec: float | None = None

    def to_dict(self) -> dict:
        return {
            "pattern_name": self.pattern_name,
            "description": self.description,
            "learned_from": self.learned_from,
            "fact_table": self.fact_table,
            "template_sql": self.template_sql,
            "variables": self.variables,
            "success_count": self.success_count,
            "last_success": self.last_success,
            "avg_runtime_sec": self.avg_runtime_sec,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueryTemplate":
        return cls(
            pattern_name=data["pattern_name"],
            description=data["description"],
            learned_from=data["learned_from"],
            fact_table=data["fact_table"],
            template_sql=data["template_sql"],
            variables=data.get("variables", []),
            success_count=data.get("success_count", 1),
            last_success=data.get("last_success", datetime.now().isoformat()),
            avg_runtime_sec=data.get("avg_runtime_sec"),
        )


class SchemaCache:
    """Manages cached schema information (concepts and tables)."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or get_cache_dir()
        self.concepts_file = self.cache_dir / "concepts.json"
        self.tables_file = self.cache_dir / "tables.json"
        self._concepts: dict[str, dict] | None = None
        self._tables: dict[str, CachedTable] | None = None

    @property
    def concepts(self) -> dict[str, dict]:
        """Lazy-load concepts cache."""
        if self._concepts is None:
            self._concepts = _load_json(self.concepts_file)
        return self._concepts

    @property
    def tables(self) -> dict[str, CachedTable]:
        """Lazy-load tables cache."""
        if self._tables is None:
            raw = _load_json(self.tables_file)
            self._tables = {k: CachedTable.from_dict(v) for k, v in raw.items()}
        return self._tables

    def save(self) -> None:
        """Persist cache to disk."""
        if self._concepts is not None:
            _save_json(self.concepts_file, self._concepts)
        if self._tables is not None:
            tables_dict = {k: v.to_dict() for k, v in self._tables.items()}
            _save_json(self.tables_file, tables_dict)

    # -------------------------------------------------------------------------
    # Concept operations
    # -------------------------------------------------------------------------

    def get_concept(self, concept: str) -> dict | None:
        """Look up a concept (e.g., 'customers' → table info)."""
        normalized = concept.lower().strip()
        return self.concepts.get(normalized)

    def set_concept(
        self,
        concept: str,
        table: str,
        key_column: str | None = None,
        date_column: str | None = None,
    ) -> None:
        """Store a concept → table mapping."""
        normalized = concept.lower().strip()
        self.concepts[normalized] = {
            "table": table,
            "key_column": key_column,
            "date_column": date_column,
            "learned_at": datetime.now().isoformat(),
        }
        self.save()
        logger.info(f"Cached concept '{normalized}' → {table}")

    def get_concepts_for_table(self, table: str) -> list[str]:
        """Find all concepts that map to a given table."""
        table_upper = table.upper()
        return [
            c for c, info in self.concepts.items() if info.get("table", "").upper() == table_upper
        ]

    # -------------------------------------------------------------------------
    # Table operations
    # -------------------------------------------------------------------------

    def get_table(self, full_name: str) -> CachedTable | None:
        """Get cached table schema by full name (DATABASE.SCHEMA.TABLE)."""
        return self.tables.get(full_name.upper())

    def set_table(self, table: CachedTable) -> None:
        """Cache a table's schema."""
        self.tables[table.full_name.upper()] = table
        self.save()
        logger.info(f"Cached table schema: {table.full_name}")

    def get_tables_in_schema(self, database: str, schema: str) -> list[CachedTable]:
        """Get all cached tables in a schema."""
        prefix = f"{database}.{schema}.".upper()
        return [t for name, t in self.tables.items() if name.startswith(prefix)]

    def invalidate_table(self, full_name: str) -> bool:
        """Remove a table from cache. Returns True if it existed."""
        key = full_name.upper()
        if key in self.tables:
            del self.tables[key]
            self.save()
            logger.info(f"Invalidated cached table: {full_name}")
            return True
        return False

    # -------------------------------------------------------------------------
    # Staleness and cleanup
    # -------------------------------------------------------------------------

    def get_stale_entries(self, ttl_days: int = DEFAULT_TTL_DAYS) -> dict[str, Any]:
        """Find all stale cache entries."""
        stale = {
            "tables": [],
            "concepts": [],
        }

        cutoff = datetime.now() - timedelta(days=ttl_days)

        for name, table in self.tables.items():
            if table.is_stale(ttl_days):
                stale["tables"].append(name)

        for concept, info in self.concepts.items():
            learned_at = info.get("learned_at")
            if learned_at:
                try:
                    if datetime.fromisoformat(learned_at) < cutoff:
                        stale["concepts"].append(concept)
                except ValueError:
                    pass

        return stale

    def purge_stale(self, ttl_days: int = DEFAULT_TTL_DAYS) -> dict[str, int]:
        """Remove all stale entries. Returns count of purged items."""
        stale = self.get_stale_entries(ttl_days)

        for table_name in stale["tables"]:
            self.tables.pop(table_name, None)

        for concept in stale["concepts"]:
            self.concepts.pop(concept, None)

        self.save()

        return {
            "tables_purged": len(stale["tables"]),
            "concepts_purged": len(stale["concepts"]),
        }

    def clear_all(self) -> None:
        """Clear entire cache."""
        self._concepts = {}
        self._tables = {}
        self.save()
        logger.info("Cleared all schema cache")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        stale = self.get_stale_entries()
        return {
            "concepts_count": len(self.concepts),
            "tables_count": len(self.tables),
            "stale_concepts": len(stale["concepts"]),
            "stale_tables": len(stale["tables"]),
            "cache_dir": str(self.cache_dir),
        }


class TemplateCache:
    """Manages learned query templates."""

    # Known question patterns with regex matchers
    PATTERNS = [
        (
            "who_uses_X",
            r"who\s+(?:is\s+)?us(?:es?|ing)\s+(.+?)(?:\?|$)",
            "Find which entities use a feature",
        ),
        ("count_X", r"how\s+many\s+(.+?)(?:\?|$)", "Count occurrences of something"),
        ("top_N_by_X", r"top\s+(\d+)\s+(.+?)\s+by\s+(.+?)(?:\?|$)", "Rank entities by a metric"),
        ("X_over_time", r"(.+?)\s+over\s+time(?:\?|$)", "Trend analysis over time"),
        ("X_by_Y", r"(.+?)\s+by\s+(.+?)(?:\?|$)", "Group metric by dimension"),
    ]

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or get_cache_dir()
        self.templates_file = self.cache_dir / "templates.json"
        self._templates: dict[str, QueryTemplate] | None = None

    @property
    def templates(self) -> dict[str, QueryTemplate]:
        """Lazy-load templates cache."""
        if self._templates is None:
            raw = _load_json(self.templates_file)
            self._templates = {k: QueryTemplate.from_dict(v) for k, v in raw.items()}
        return self._templates

    def save(self) -> None:
        """Persist cache to disk."""
        if self._templates is not None:
            templates_dict = {k: v.to_dict() for k, v in self._templates.items()}
            _save_json(self.templates_file, templates_dict)

    def match_pattern(self, question: str) -> tuple[str, list[str]] | None:
        """Try to match a question to a known pattern.

        Returns (pattern_name, captured_variables) or None.
        """
        question_lower = question.lower().strip()

        for pattern_name, regex, _ in self.PATTERNS:
            match = re.search(regex, question_lower, re.IGNORECASE)
            if match:
                return (pattern_name, list(match.groups()))

        return None

    def get_template(self, pattern_name: str) -> QueryTemplate | None:
        """Get a template by pattern name."""
        return self.templates.get(pattern_name)

    def find_template_for_question(self, question: str) -> tuple[QueryTemplate, list[str]] | None:
        """Find a matching template for a question.

        Returns (template, variables) or None.
        """
        match = self.match_pattern(question)
        if match:
            pattern_name, variables = match
            template = self.get_template(pattern_name)
            if template:
                return (template, variables)
        return None

    def store_template(
        self,
        pattern_name: str,
        description: str,
        learned_from: str,
        fact_table: str,
        template_sql: str,
        variables: list[str],
        runtime_sec: float | None = None,
    ) -> QueryTemplate:
        """Store a new query template."""
        template = QueryTemplate(
            pattern_name=pattern_name,
            description=description,
            learned_from=learned_from,
            fact_table=fact_table,
            template_sql=template_sql,
            variables=variables,
            avg_runtime_sec=runtime_sec,
        )
        self.templates[pattern_name] = template
        self.save()
        logger.info(f"Stored query template: {pattern_name}")
        return template

    def record_success(self, pattern_name: str, runtime_sec: float | None = None) -> None:
        """Record a successful use of a template."""
        template = self.templates.get(pattern_name)
        if template:
            template.success_count += 1
            template.last_success = datetime.now().isoformat()
            if runtime_sec and template.avg_runtime_sec:
                # Running average
                template.avg_runtime_sec = template.avg_runtime_sec * 0.8 + runtime_sec * 0.2
            elif runtime_sec:
                template.avg_runtime_sec = runtime_sec
            self.save()

    def clear_all(self) -> None:
        """Clear all templates."""
        self._templates = {}
        self.save()
        logger.info("Cleared all query templates")

    def get_stats(self) -> dict[str, Any]:
        """Get template statistics."""
        return {
            "templates_count": len(self.templates),
            "templates": [
                {
                    "pattern": t.pattern_name,
                    "success_count": t.success_count,
                    "last_success": t.last_success,
                }
                for t in self.templates.values()
            ],
        }


# Global cache instances (lazy-loaded)
_schema_cache: SchemaCache | None = None
_template_cache: TemplateCache | None = None


def get_schema_cache() -> SchemaCache:
    """Get the global schema cache instance."""
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = SchemaCache()
    return _schema_cache


def get_template_cache() -> TemplateCache:
    """Get the global template cache instance."""
    global _template_cache
    if _template_cache is None:
        _template_cache = TemplateCache()
    return _template_cache
