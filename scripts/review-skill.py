#!/usr/bin/env python3
"""
Skill Review Sub-Agent for Ralph Loop.

Reviews skill changes against Anthropic's best practices to prevent overfitting
and ensure skills are effective across different queries.

Usage:
    python scripts/review-skill.py <skill_path> [--original <original_path>]
    python scripts/review-skill.py shared-skills/analyzing-data/SKILL.md

Output: JSON with pass/fail status and specific issues found.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Issue:
    severity: str  # "error", "warning", "info"
    rule: str
    message: str
    line: Optional[int] = None


@dataclass
class ReviewResult:
    skill_path: str
    pass_review: bool
    score: int  # 0-100
    issues: list[Issue] = field(default_factory=list)
    summary: str = ""

    def to_dict(self):
        return {
            "skill_path": self.skill_path,
            "pass": self.pass_review,
            "score": self.score,
            "issues": [asdict(i) for i in self.issues],
            "summary": self.summary,
        }


def count_lines(content: str) -> int:
    """Count non-empty lines in content."""
    return len([line for line in content.split("\n") if line.strip()])


def check_frontmatter(content: str) -> list[Issue]:
    """Check YAML frontmatter requirements."""
    issues = []

    # Check for frontmatter
    if not content.startswith("---"):
        issues.append(
            Issue(
                severity="error",
                rule="frontmatter-required",
                message="SKILL.md must start with YAML frontmatter (---)",
            )
        )
        return issues

    # Extract frontmatter
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        issues.append(
            Issue(
                severity="error",
                rule="frontmatter-format",
                message="Invalid YAML frontmatter format",
            )
        )
        return issues

    frontmatter = match.group(1)

    # Check name field
    name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.MULTILINE)
    if not name_match:
        issues.append(
            Issue(
                severity="error",
                rule="name-required",
                message="Frontmatter must include 'name' field",
            )
        )
    else:
        name = name_match.group(1).strip()
        if len(name) > 64:
            issues.append(
                Issue(
                    severity="error",
                    rule="name-length",
                    message=f"Name must be <= 64 chars (got {len(name)})",
                )
            )
        if not re.match(r"^[a-z0-9-]+$", name):
            issues.append(
                Issue(
                    severity="error",
                    rule="name-format",
                    message="Name must be lowercase letters, numbers, hyphens only",
                )
            )

    # Check description field
    desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    if not desc_match:
        issues.append(
            Issue(
                severity="error",
                rule="description-required",
                message="Frontmatter must include 'description' field",
            )
        )
    else:
        desc = desc_match.group(1).strip()
        if len(desc) > 1024:
            issues.append(
                Issue(
                    severity="error",
                    rule="description-length",
                    message=f"Description must be <= 1024 chars (got {len(desc)})",
                )
            )
        # Check for "when to use" in description
        when_patterns = ["use when", "when", "for", "if the user"]
        if not any(p in desc.lower() for p in when_patterns):
            issues.append(
                Issue(
                    severity="warning",
                    rule="description-when",
                    message="Description should include WHEN to use the skill, not just WHAT it does",
                )
            )

    return issues


def check_length(content: str) -> list[Issue]:
    """Check skill length is under 500 lines."""
    issues = []
    lines = count_lines(content)

    if lines > 500:
        issues.append(
            Issue(
                severity="error",
                rule="length-limit",
                message=f"SKILL.md body should be under 500 lines (got {lines}). Split into reference files.",
            )
        )
    elif lines > 400:
        issues.append(
            Issue(
                severity="warning",
                rule="length-warning",
                message=f"SKILL.md is {lines} lines. Consider splitting content into reference files.",
            )
        )

    return issues


def check_nested_references(content: str, skill_dir: Path) -> list[Issue]:
    """Check that references are one level deep."""
    issues = []

    # Find all markdown links to .md files
    links = re.findall(r"\[.*?\]\(([^)]+\.md)\)", content)

    for link in links:
        ref_path = skill_dir / link
        if ref_path.exists():
            ref_content = ref_path.read_text()
            # Check if reference file has its own .md links
            nested_links = re.findall(r"\[.*?\]\(([^)]+\.md)\)", ref_content)
            if nested_links:
                issues.append(
                    Issue(
                        severity="error",
                        rule="one-level-deep",
                        message=f"Reference '{link}' has nested references to: {nested_links}. Keep references one level deep from SKILL.md.",
                    )
                )

    return issues


def check_overfitting(content: str) -> list[Issue]:
    """Check for signs of overfitting to specific test cases."""
    issues = []

    # Check for hardcoded specific values that might be test-specific
    # Overfitting patterns: very specific operator names, very specific URLs for one feature

    # Count how many specific operator names are mentioned
    operator_mentions = re.findall(
        r"[A-Z][a-z]+(?:Operator|Sensor|Hook|Transfer)", content
    )
    unique_operators = set(operator_mentions)

    if len(unique_operators) > 5:
        issues.append(
            Issue(
                severity="warning",
                rule="overfitting-operators",
                message=f"Skill mentions {len(unique_operators)} specific operators. Consider using patterns/discovery instead of hardcoded lists.",
            )
        )

    # Check for very specific instructions that only apply to one case
    specific_patterns = [
        (r"MUST.*ApprovalOperator", "overfitting-specific-operator"),
        (r"ALWAYS.*HITL", "overfitting-specific-feature"),
        (r"before.*HITL", "overfitting-specific-sequence"),
    ]

    for pattern, rule in specific_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            issues.append(
                Issue(
                    severity="info",
                    rule=rule,
                    message=f"Pattern '{pattern}' may be overfitting to a specific test case. Ensure this applies generally.",
                )
            )

    return issues


def check_conciseness(content: str) -> list[Issue]:
    """Check for verbose patterns that should be simplified."""
    issues = []

    verbose_patterns = [
        (
            r"PDF \(Portable Document Format\)",
            "Explaining what PDF means - Claude knows this",
        ),
        (
            r"JSON \(JavaScript Object Notation\)",
            "Explaining what JSON means - Claude knows this",
        ),
        (
            r"SQL \(Structured Query Language\)",
            "Explaining what SQL means - Claude knows this",
        ),
        (r"There are many (?:ways|methods|approaches)", "Offering too many options"),
        (
            r"You can use .* or .* or .* or",
            "Offering too many options - provide a default",
        ),
    ]

    for pattern, message in verbose_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            issues.append(Issue(severity="info", rule="conciseness", message=message))

    return issues


def check_workflow_structure(content: str) -> list[Issue]:
    """Check for proper workflow structure."""
    issues = []

    # Check if there's a workflow or complex task
    has_multiple_steps = len(re.findall(r"^#+\s*Step\s*\d", content, re.MULTILINE)) > 2

    if has_multiple_steps:
        # Should have a checklist
        has_checklist = "- [ ]" in content or "- [x]" in content
        if not has_checklist:
            issues.append(
                Issue(
                    severity="warning",
                    rule="workflow-checklist",
                    message="Complex workflow detected but no checklist found. Add a copyable checklist for multi-step tasks.",
                )
            )

    return issues


def check_terminology_consistency(content: str) -> list[Issue]:
    """Check for inconsistent terminology."""
    issues = []

    inconsistent_terms = [
        (["API endpoint", "URL", "API route", "path"], "API terminology"),
        (["field", "box", "element", "control"], "form field terminology"),
        (["extract", "pull", "get", "retrieve"], "data retrieval terminology"),
    ]

    for terms, category in inconsistent_terms:
        found = [t for t in terms if t.lower() in content.lower()]
        if len(found) > 2:
            issues.append(
                Issue(
                    severity="info",
                    rule="terminology-consistency",
                    message=f"Inconsistent {category}: using {found}. Pick one term and use it consistently.",
                )
            )

    return issues


def check_freedom_level(content: str) -> list[Issue]:
    """Check if freedom level matches task type."""
    issues = []

    # High constraint language
    constraint_words = len(
        re.findall(r"\b(MUST|ALWAYS|NEVER|REQUIRED|MANDATORY)\b", content)
    )
    total_words = len(content.split())

    constraint_ratio = constraint_words / max(total_words, 1)

    if constraint_ratio > 0.01:  # More than 1% constraint words
        issues.append(
            Issue(
                severity="info",
                rule="freedom-level",
                message=f"High constraint density ({constraint_words} MUST/ALWAYS/NEVER words). Ensure this level of strictness is justified.",
            )
        )

    return issues


def review_skill(skill_path: str, original_path: Optional[str] = None) -> ReviewResult:
    """Review a skill file against best practices."""
    path = Path(skill_path)

    if not path.exists():
        return ReviewResult(
            skill_path=skill_path,
            pass_review=False,
            score=0,
            summary=f"Skill file not found: {skill_path}",
        )

    content = path.read_text()
    skill_dir = path.parent

    all_issues: list[Issue] = []

    # Run all checks
    all_issues.extend(check_frontmatter(content))
    all_issues.extend(check_length(content))
    all_issues.extend(check_nested_references(content, skill_dir))
    all_issues.extend(check_overfitting(content))
    all_issues.extend(check_conciseness(content))
    all_issues.extend(check_workflow_structure(content))
    all_issues.extend(check_terminology_consistency(content))
    all_issues.extend(check_freedom_level(content))

    # Calculate score
    error_count = len([i for i in all_issues if i.severity == "error"])
    warning_count = len([i for i in all_issues if i.severity == "warning"])
    info_count = len([i for i in all_issues if i.severity == "info"])

    score = max(0, 100 - (error_count * 20) - (warning_count * 5) - (info_count * 1))
    pass_review = error_count == 0

    # Generate summary
    if pass_review and score >= 80:
        summary = f"Skill passes review with score {score}/100."
    elif pass_review:
        summary = f"Skill passes with warnings. Score: {score}/100. Consider addressing {warning_count} warnings."
    else:
        summary = f"Skill FAILS review. Score: {score}/100. Fix {error_count} errors before proceeding."

    return ReviewResult(
        skill_path=skill_path,
        pass_review=pass_review,
        score=score,
        issues=all_issues,
        summary=summary,
    )


def main():
    parser = argparse.ArgumentParser(description="Review skill against best practices")
    parser.add_argument("skill_path", help="Path to SKILL.md file")
    parser.add_argument(
        "--original", help="Path to original SKILL.md for diff comparison"
    )
    parser.add_argument(
        "--format", choices=["json", "text"], default="text", help="Output format"
    )

    args = parser.parse_args()

    result = review_skill(args.skill_path, args.original)

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"SKILL REVIEW: {result.skill_path}")
        print(f"{'='*60}")
        print(f"\nResult: {'PASS' if result.pass_review else 'FAIL'}")
        print(f"Score: {result.score}/100")
        print(f"\n{result.summary}")

        if result.issues:
            print(f"\n{'Issues Found':=^60}")
            for issue in result.issues:
                icon = {"error": "[X]", "warning": "[!]", "info": "[i]"}[issue.severity]
                print(f"\n{icon} [{issue.severity.upper()}] {issue.rule}")
                print(f"    {issue.message}")

        print(f"\n{'='*60}\n")

    sys.exit(0 if result.pass_review else 1)


if __name__ == "__main__":
    main()
