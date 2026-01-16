"""Persistent cache for schema discovery and query templates.

Cache files are stored at ~/.astro/ai/cache/:
- concepts.json: concept → table mapping (e.g., "customers" → "HQ.MODEL.ORGS")
- tables.json: table → columns, row_count, description
- templates.json: question pattern → query template
- cache_meta.json: TTL settings, validation timestamps
"""

import json
import logging
import os
import re
import tempfile
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


@dataclass
class QueryPattern:
    """A learned query pattern/strategy for a type of question.

    Unlike QueryTemplate (which stores SQL with placeholders), QueryPattern
    captures procedural knowledge: strategies, gotchas, and multi-step approaches.
    """

    pattern_name: str  # e.g., "operator_usage"
    question_types: list[str]  # e.g., ["who uses X", "which customers use X"]
    strategy: list[str]  # Step-by-step approach that worked
    tables_used: list[str]  # Tables involved
    gotchas: list[str]  # What to avoid / what failed
    example_query: str | None = None  # Working SQL example
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ttl_days: int = 90  # Auto-expire after N days
    success_count: int = 1
    failure_count: int = 0

    def to_dict(self) -> dict:
        return {
            "pattern_name": self.pattern_name,
            "question_types": self.question_types,
            "strategy": self.strategy,
            "tables_used": self.tables_used,
            "gotchas": self.gotchas,
            "example_query": self.example_query,
            "created_at": self.created_at,
            "ttl_days": self.ttl_days,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QueryPattern":
        return cls(
            pattern_name=data["pattern_name"],
            question_types=data.get("question_types", []),
            strategy=data.get("strategy", []),
            tables_used=data.get("tables_used", []),
            gotchas=data.get("gotchas", []),
            example_query=data.get("example_query"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            ttl_days=data.get("ttl_days", 90),
            success_count=data.get("success_count", 1),
            failure_count=data.get("failure_count", 0),
        )

    def is_stale(self) -> bool:
        """Check if pattern is older than its TTL."""
        created = datetime.fromisoformat(self.created_at)
        return datetime.now() - created > timedelta(days=self.ttl_days)

    def should_be_purged(self) -> bool:
        """Check if pattern should be auto-deleted.

        Purge if: stale AND (low usage OR more failures than successes)
        """
        if not self.is_stale():
            return False
        return self.success_count < 3 or self.failure_count > self.success_count


class PatternCache:
    """Manages learned query patterns (procedural knowledge).

    Patterns capture strategies and gotchas for question types, not SQL templates.
    """

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or get_cache_dir()
        self.patterns_file = self.cache_dir / "patterns.json"
        self._patterns: dict[str, QueryPattern] | None = None

    @property
    def patterns(self) -> dict[str, QueryPattern]:
        """Lazy-load patterns cache."""
        if self._patterns is None:
            raw = _load_json(self.patterns_file)
            self._patterns = {k: QueryPattern.from_dict(v) for k, v in raw.items()}
        return self._patterns

    def save(self) -> None:
        """Persist cache to disk."""
        if self._patterns is not None:
            patterns_dict = {k: v.to_dict() for k, v in self._patterns.items()}
            _save_json(self.patterns_file, patterns_dict)

    def get_pattern(self, pattern_name: str) -> QueryPattern | None:
        """Get a pattern by name."""
        return self.patterns.get(pattern_name.lower().strip())

    def lookup_by_question(self, question: str) -> list[QueryPattern]:
        """Find patterns that match a question.

        Uses keyword matching against question_types.
        Returns all matching patterns, sorted by success_count.
        """
        question_lower = question.lower()
        matches = []

        for pattern in self.patterns.values():
            for question_type in pattern.question_types:
                # Simple keyword matching - check if question type words appear in question
                keywords = question_type.lower().replace("x", "").split()
                if all(kw in question_lower for kw in keywords if len(kw) > 2):
                    matches.append(pattern)
                    break

        # Sort by success_count (most successful first)
        return sorted(matches, key=lambda p: p.success_count, reverse=True)

    def store_pattern(
        self,
        pattern_name: str,
        question_types: list[str],
        strategy: list[str],
        tables_used: list[str],
        gotchas: list[str],
        example_query: str | None = None,
        ttl_days: int = 90,
    ) -> QueryPattern:
        """Store a new query pattern."""
        pattern = QueryPattern(
            pattern_name=pattern_name,
            question_types=question_types,
            strategy=strategy,
            tables_used=tables_used,
            gotchas=gotchas,
            example_query=example_query,
            ttl_days=ttl_days,
        )
        self.patterns[pattern_name.lower().strip()] = pattern
        self.save()
        logger.info(f"Stored query pattern: {pattern_name}")
        return pattern

    def record_success(self, pattern_name: str) -> None:
        """Record a successful use of a pattern."""
        pattern = self.patterns.get(pattern_name.lower().strip())
        if pattern:
            pattern.success_count += 1
            self.save()
            logger.info(f"Pattern '{pattern_name}' success count: {pattern.success_count}")

    def record_failure(self, pattern_name: str) -> None:
        """Record a failed use of a pattern."""
        pattern = self.patterns.get(pattern_name.lower().strip())
        if pattern:
            pattern.failure_count += 1
            self.save()
            logger.warning(f"Pattern '{pattern_name}' failure count: {pattern.failure_count}")

    def delete_pattern(self, pattern_name: str) -> bool:
        """Delete a pattern. Returns True if it existed."""
        key = pattern_name.lower().strip()
        if key in self.patterns:
            del self.patterns[key]
            self.save()
            logger.info(f"Deleted pattern: {pattern_name}")
            return True
        return False

    def purge_stale(self) -> list[str]:
        """Remove patterns that should be purged. Returns list of purged names."""
        purged = []
        for name, pattern in list(self.patterns.items()):
            if pattern.should_be_purged():
                del self.patterns[name]
                purged.append(name)
                logger.info(f"Auto-purged stale pattern: {name}")

        if purged:
            self.save()
        return purged

    def clear_all(self) -> None:
        """Clear all patterns."""
        self._patterns = {}
        self.save()
        logger.info("Cleared all query patterns")

    def get_stats(self) -> dict[str, Any]:
        """Get pattern statistics."""
        stale_count = sum(1 for p in self.patterns.values() if p.is_stale())
        return {
            "patterns_count": len(self.patterns),
            "stale_count": stale_count,
            "patterns": [
                {
                    "name": p.pattern_name,
                    "question_types": p.question_types,
                    "success_count": p.success_count,
                    "failure_count": p.failure_count,
                    "is_stale": p.is_stale(),
                }
                for p in self.patterns.values()
            ],
        }

    def list_patterns(self) -> list[dict]:
        """List all patterns with summary info."""
        return [
            {
                "name": p.pattern_name,
                "question_types": p.question_types,
                "tables_used": p.tables_used,
                "success_count": p.success_count,
                "created_at": p.created_at,
            }
            for p in self.patterns.values()
        ]


# Global cache instances (lazy-loaded)
_schema_cache: SchemaCache | None = None
_template_cache: TemplateCache | None = None
_pattern_cache: PatternCache | None = None


def get_schema_cache() -> SchemaCache:
    """Get the global schema cache instance."""
    global _schema_cache
    # Support disabling cache for A/B testing (used by split-test.py)
    if os.environ.get("DISABLE_CONCEPT_CACHE", "").lower() == "true":
        # Return a fresh, non-persisting cache in temp directory
        return SchemaCache(cache_dir=Path(tempfile.gettempdir()) / "disabled-cache")
    if _schema_cache is None:
        _schema_cache = SchemaCache()
    return _schema_cache


def get_template_cache() -> TemplateCache:
    """Get the global template cache instance."""
    global _template_cache
    if _template_cache is None:
        _template_cache = TemplateCache()
    return _template_cache


def get_pattern_cache() -> PatternCache:
    """Get the global pattern cache instance."""
    global _pattern_cache
    if _pattern_cache is None:
        _pattern_cache = PatternCache()
    return _pattern_cache


def load_concepts_from_warehouse_md(path: Path | None = None) -> int:
    """Parse warehouse.md and populate cache with Quick Reference entries.

    Looks for the Quick Reference table in warehouse.md and loads all
    concept → table mappings into the cache.

    Args:
        path: Path to warehouse.md. If None, searches common locations.

    Returns:
        Number of concepts loaded into cache.
    """
    # Find warehouse.md if not provided
    if path is None:
        locations = [
            Path(".astro/warehouse.md"),
            Path.home() / ".astro" / "ai" / "config" / "warehouse.md",
        ]
        for loc in locations:
            if loc.exists():
                path = loc
                break

    if path is None or not path.exists():
        logger.warning("warehouse.md not found")
        return 0

    content = path.read_text(encoding="utf-8")

    # Parse Quick Reference table
    # Format: | concept | TABLE | KEY_COL | DATE_COL |
    concepts_loaded = 0
    in_quick_ref = False
    schema_cache = get_schema_cache()

    for line in content.split("\n"):
        line = line.strip()

        # Detect Quick Reference section
        if "## Quick Reference" in line:
            in_quick_ref = True
            continue

        # Stop at next section
        if in_quick_ref and line.startswith("## ") and "Quick Reference" not in line:
            break

        # Skip non-table lines
        if not in_quick_ref or not line.startswith("|"):
            continue

        # Skip header and separator rows
        if "Concept" in line or "---" in line or "Table" in line:
            continue

        # Parse table row: | concept | table | key_col | date_col |
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p]  # Remove empty strings

        if len(parts) >= 2:
            concept = parts[0].lower()
            table = parts[1]
            key_column = parts[2] if len(parts) > 2 and parts[2] != "-" else None
            date_column = parts[3] if len(parts) > 3 and parts[3] != "-" else None

            # Skip if table doesn't look valid (should have dots)
            if "." not in table:
                continue

            schema_cache.set_concept(concept, table, key_column, date_column)
            concepts_loaded += 1
            logger.info(f"Loaded concept from warehouse.md: {concept} → {table}")

    return concepts_loaded
