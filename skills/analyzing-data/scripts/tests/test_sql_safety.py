"""Tests for SQL safety module."""

import pytest
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from sql_safety import (
    check_sql_safety,
    is_select_only,
    get_statement_type,
    has_limit,
    inject_limit,
)


class TestCheckSqlSafety:
    """Tests for check_sql_safety function."""

    def test_select_is_safe(self):
        is_safe, ops = check_sql_safety("SELECT * FROM users")
        assert is_safe is True
        assert ops == []

    def test_select_with_join_is_safe(self):
        is_safe, ops = check_sql_safety(
            "SELECT u.*, o.name FROM users u JOIN orgs o ON u.org_id = o.id"
        )
        assert is_safe is True
        assert ops == []

    def test_select_with_cte_is_safe(self):
        is_safe, ops = check_sql_safety(
            "WITH cte AS (SELECT * FROM users) SELECT * FROM cte"
        )
        assert is_safe is True
        assert ops == []

    def test_select_with_truncate_in_string_literal_is_safe(self):
        """Ensure TRUNCATE in string literals doesn't trigger false positive."""
        is_safe, ops = check_sql_safety("SELECT 'TRUNCATE TABLE users' AS msg")
        assert is_safe is True
        assert ops == []

    def test_select_with_truncate_in_comment_is_safe(self):
        """Ensure TRUNCATE in comments doesn't trigger false positive."""
        is_safe, ops = check_sql_safety(
            "SELECT * FROM users -- TRUNCATE TABLE users"
        )
        assert is_safe is True
        assert ops == []

    def test_create_is_blocked(self):
        is_safe, ops = check_sql_safety("CREATE TABLE test (id INT)")
        assert is_safe is False
        assert "CREATE" in ops

    def test_drop_is_blocked(self):
        is_safe, ops = check_sql_safety("DROP TABLE users")
        assert is_safe is False
        assert "DROP" in ops

    def test_delete_is_blocked(self):
        is_safe, ops = check_sql_safety("DELETE FROM users WHERE id = 1")
        assert is_safe is False
        assert "DELETE" in ops

    def test_update_is_blocked(self):
        is_safe, ops = check_sql_safety("UPDATE users SET name = 'test' WHERE id = 1")
        assert is_safe is False
        assert "UPDATE" in ops

    def test_insert_is_blocked(self):
        is_safe, ops = check_sql_safety("INSERT INTO users (name) VALUES ('test')")
        assert is_safe is False
        assert "INSERT" in ops

    def test_alter_is_blocked(self):
        is_safe, ops = check_sql_safety("ALTER TABLE users ADD COLUMN age INT")
        assert is_safe is False
        assert "ALTER" in ops

    def test_truncate_is_blocked(self):
        is_safe, ops = check_sql_safety("TRUNCATE TABLE users")
        assert is_safe is False
        assert "TRUNCATE" in ops

    def test_create_as_select_is_blocked(self):
        is_safe, ops = check_sql_safety(
            "CREATE TABLE new_table AS SELECT * FROM users"
        )
        assert is_safe is False
        assert "CREATE" in ops


class TestIsSelectOnly:
    """Tests for is_select_only function."""

    def test_simple_select(self):
        assert is_select_only("SELECT * FROM users") is True

    def test_select_with_cte(self):
        assert is_select_only(
            "WITH cte AS (SELECT * FROM users) SELECT * FROM cte"
        ) is True

    def test_insert_is_not_select(self):
        assert is_select_only("INSERT INTO users VALUES (1)") is False

    def test_create_is_not_select(self):
        assert is_select_only("CREATE TABLE test (id INT)") is False


class TestGetStatementType:
    """Tests for get_statement_type function."""

    def test_select(self):
        assert get_statement_type("SELECT * FROM users") == "SELECT"

    def test_insert(self):
        assert get_statement_type("INSERT INTO users VALUES (1)") == "INSERT"

    def test_update(self):
        assert get_statement_type("UPDATE users SET name = 'x'") == "UPDATE"

    def test_delete(self):
        assert get_statement_type("DELETE FROM users") == "DELETE"

    def test_create(self):
        assert get_statement_type("CREATE TABLE test (id INT)") == "CREATE"

    def test_drop(self):
        assert get_statement_type("DROP TABLE users") == "DROP"


class TestHasLimit:
    """Tests for has_limit function."""

    def test_no_limit(self):
        assert has_limit("SELECT * FROM users") is False

    def test_with_limit(self):
        assert has_limit("SELECT * FROM users LIMIT 10") is True

    def test_limit_in_subquery(self):
        # Main query doesn't have limit, subquery does
        query = "SELECT * FROM (SELECT * FROM users LIMIT 10) sub"
        # This should detect the LIMIT in the subquery
        assert has_limit(query) is True

    def test_cte_with_limit(self):
        assert has_limit(
            "WITH cte AS (SELECT * FROM users) SELECT * FROM cte LIMIT 5"
        ) is True


class TestInjectLimit:
    """Tests for inject_limit function."""

    def test_injects_limit(self):
        result = inject_limit("SELECT * FROM users", 100)
        assert result == "SELECT * FROM users LIMIT 100"

    def test_preserves_existing_limit(self):
        query = "SELECT * FROM users LIMIT 50"
        result = inject_limit(query, 100)
        assert result == query  # Unchanged

    def test_strips_semicolon(self):
        result = inject_limit("SELECT * FROM users;", 100)
        assert result == "SELECT * FROM users LIMIT 100"

    def test_does_not_inject_for_insert(self):
        query = "INSERT INTO users VALUES (1)"
        result = inject_limit(query, 100)
        assert result == query  # Unchanged for non-SELECT

    def test_does_not_inject_for_create(self):
        query = "CREATE TABLE test AS SELECT * FROM users"
        result = inject_limit(query, 100)
        assert result == query  # Unchanged for non-SELECT
