---
name: ruff-airflow-rule
description: This skill should be used when the user asks to "add a new airflow rule", "create an airflow lint rule", "implement an airflow inspection", "new AIR rule", or discusses creating Ruff linter rules in the airflow category.
---

# Creating a New Airflow Lint Rule in Ruff

This skill guides creating new Airflow-specific lint rules (AIR prefix) in the Ruff codebase.

## Pre-Implementation: Gather Context

**Before writing any code, ask the user the following questions (if not already answered in their request):**

1. **Airflow version target:**
> Which version of Airflow does this rule target?
> - Airflow 2 only
> - Airflow 3 onward
> - Both Airflow 2 and 3

2. **DAG API targeting** (for general best-practice rules AIR001-099 only):
> Airflow DAGs can be written using the TaskFlow API (decorators like `@task.branch`) or the standard operator API (`BranchPythonOperator`). Both are equally supported. Should this rule target:
> - TaskFlow API only (decorator-based)
> - Operator API only (operator-based)
> - Both (recommended — the rule should be DAG implementation-agnostic)
>
> If both: the rule will need two entry points — a statement-level dispatch for decorated functions and an expression-level dispatch for operator calls. Use a shared helper for the core analysis logic, and a `Kind` enum on the violation struct to produce context-specific diagnostic messages for each form.

3. **Local Airflow repository for validation:**
> Do you have a local clone of the Airflow repository? If so, provide the path (e.g., `~/repositories/airflow`).

If a local Airflow repo is available, use it after implementation to validate the rule against real-world code and check for false positives (see "Post-Implementation: Validate Against Airflow" below).

**Code prefix validation:** If a rule targets Airflow 3 (onward), its code MUST start with `AIR3##` (e.g., AIR301, AIR302, AIR311). If the user specified a code that doesn't follow this pattern, WARN them before proceeding.

**Important distinction for AIR3xx rules:** AIR3xx rules are migration rules that flag *old-style* (Airflow 2) imports/patterns to help migrate to Airflow 3. They should only match deprecated import paths — NOT the new `airflow.sdk` paths (which are the correct replacements). However, shared helpers that check context (e.g., "is this function decorated with `@task`?") should match both old and new paths, since deprecated patterns inside a task function need to be flagged regardless of which import style the decorator uses.

## Rule Numbering Scheme

Understand which category your rule belongs to before picking a code:

| Range | Category | Description |
|-------|----------|-------------|
| AIR001-099 | General best-practice | Style, readability, common mistakes (not version-specific) |
| AIR201-299 | >=2.x best-practice | Best practices for features available since Airflow 2.x |
| AIR301 | Removed in 3.0 | Symbols/args fully removed in Airflow 3.0 with no compat layer |
| AIR302 | Moved to provider in 3.0 | Symbols moved to external provider packages (required migration) |
| AIR303 | Signature change in 3.0 | Function/method signatures changed (args renamed, reordered, etc.) |
| AIR311 | Suggested update for 3.0 | Deprecated with compat layer — still works but will break later |
| AIR312 | Suggested provider move for 3.0 | Deprecated compat layer for provider migrations |
| AIR321 | Moved in 3.1 | Symbols moved/deprecated in Airflow 3.1 |

## Airflow 2-to-3 Import Path Mapping

Rules that target **both Airflow 2 and 3** must handle both old (deprecated) and new (`airflow.sdk`) import paths. Match against both in `qualified_name.segments()`:

| Old Import Path (Deprecated) | New Import Path (airflow.sdk) |
|------------------------------|-------------------------------|
| `airflow.decorators.dag` | `airflow.sdk.dag` |
| `airflow.decorators.task` | `airflow.sdk.task` |
| `airflow.decorators.task_group` | `airflow.sdk.task_group` |
| `airflow.decorators.setup` | `airflow.sdk.setup` |
| `airflow.decorators.teardown` | `airflow.sdk.teardown` |
| `airflow.models.dag.DAG` | `airflow.sdk.DAG` |
| `airflow.models.baseoperator.BaseOperator` | `airflow.sdk.BaseOperator` |
| `airflow.models.param.Param` | `airflow.sdk.Param` |
| `airflow.models.param.ParamsDict` | `airflow.sdk.ParamsDict` |
| `airflow.models.baseoperatorlink.BaseOperatorLink` | `airflow.sdk.BaseOperatorLink` |
| `airflow.sensors.base.BaseSensorOperator` | `airflow.sdk.BaseSensorOperator` |
| `airflow.hooks.base.BaseHook` | `airflow.sdk.BaseHook` |
| `airflow.notifications.basenotifier.BaseNotifier` | `airflow.sdk.BaseNotifier` |
| `airflow.utils.task_group.TaskGroup` | `airflow.sdk.TaskGroup` |
| `airflow.utils.context.Context` | `airflow.sdk.Context` |
| `airflow.datasets.Dataset` | `airflow.sdk.Asset` |
| `airflow.datasets.DatasetAlias` | `airflow.sdk.AssetAlias` |
| `airflow.datasets.DatasetAll` | `airflow.sdk.AssetAll` |
| `airflow.datasets.DatasetAny` | `airflow.sdk.AssetAny` |
| `airflow.models.connection.Connection` | `airflow.sdk.Connection` |
| `airflow.models.variable.Variable` | `airflow.sdk.Variable` |
| `airflow.io.*` | `airflow.sdk.io.*` |

Example pattern for matching both paths:
```rust
match qualified_name.segments() {
    // Match both old and new import paths
    ["airflow", "decorators", "task"] | ["airflow", "sdk", "task"] => { /* ... */ }
    ["airflow", "models", "dag", "DAG"] | ["airflow", "sdk", "DAG"] => { /* ... */ }
    _ => return,
}
```

## Checklist

Follow these steps in order. Each step is mandatory.

### 0. Search for Reusable Utilities

**Before writing rule logic**, search for existing utilities that can be reused:

- **`ruff_python_semantic`**: Check `SemanticModel` methods (e.g., `resolve_qualified_name`, `match_builtin_expr`, `match_typing_expr`) and `analyze/visibility.rs` for decorator-checking patterns.
- **`ruff_python_ast`**: Check `helpers.rs` for AST traversal utilities (e.g., `map_callable`, `ReturnStatementVisitor`).
- **`ruff_python_trivia::Cursor`**: For rules that need ad-hoc parsing of string content (e.g., Jinja templates, SQL fragments), use `Cursor` instead of chaining `strip_prefix`/`strip_suffix`/`find`. It provides `eat_char`, `eat_while`, `eat_if`, `as_str()` for slices, and `skip_bytes`. Extract small helpers like `eat_whitespace`, `parse_identifier`, and `parse_quoted_string` for reuse within the rule (see AIR201 for an example).
- **`crate::rules::airflow::helpers`**: Check for existing airflow-specific helpers (e.g., `is_guarded_by_try_except`, `is_airflow_builtin_or_provider`, `is_method_in_subclass`, `generate_import_edit`).
- **Existing airflow rules**: Check rules like AIR301 (`removal_in_3.rs`) for patterns that may already exist or could be extracted.

**If a pattern would be useful in multiple rules, extract it into `helpers.rs` as a shared utility** rather than duplicating code. For example, AIR301 contains `is_airflow_task()` — if another rule needs the same check, move it to `helpers.rs`.

### 1. Choose a Rule Code and Name

- Check existing codes in `crates/ruff_linter/src/codes.rs` under the `// airflow` section.
- Pick the next available code in the appropriate range.
- Name the struct following the convention: the name should make sense as "allow ${name}". For example, `TaskBranchAsShortCircuit` reads as "allow task branch as short circuit".
- Do NOT use prefixes like `Disallow` or `Banned`.

### 2. Create the Rule File

Create `crates/ruff_linter/src/rules/airflow/rules/<snake_case_name>.rs`.

Choose the template below based on rule category.

#### Template: General Best-Practice Rule (AIR001-099)

```rust
use ruff_macros::{ViolationMetadata, derive_message_formats};
use ruff_python_ast::{self as ast};
use ruff_python_semantic::Modules;
use ruff_text_size::Ranged;

use crate::Violation;
use crate::checkers::ast::Checker;

/// ## What it does
/// <One-line description of what the rule checks for.>
///
/// ## Why is this bad?
/// <Explanation of why the flagged pattern is problematic.>
///
/// ## Example
/// ```python
/// <Python code that triggers the violation>
/// ```
///
/// Use instead:
/// ```python
/// <Corrected Python code>
/// ```
#[derive(ViolationMetadata)]
#[violation_metadata(preview_since = "NEXT_RUFF_VERSION")]
pub(crate) struct MyRuleName;

impl Violation for MyRuleName {
    #[derive_message_formats]
    fn message(&self) -> String {
        "<Diagnostic message shown to the user>".to_string()
    }
}

/// AIRxxx
pub(crate) fn my_rule_name(checker: &Checker, /* appropriate AST node */) {
    if !checker.semantic().seen_module(Modules::AIRFLOW) {
        return;
    }

    // Rule logic here...

    checker.report_diagnostic(MyRuleName, node.range());
}
```

#### Template: Airflow 3 Migration Rule (AIR3xx)

For rules that flag removed/moved/renamed symbols, use the existing infrastructure in `helpers.rs`:

```rust
use ruff_macros::{ViolationMetadata, derive_message_formats};
use ruff_python_ast::{self as ast, Expr};
use ruff_python_semantic::Modules;
use ruff_text_size::Ranged;

use crate::{FixAvailability, Violation};
use crate::checkers::ast::Checker;
use crate::rules::airflow::helpers::{Replacement, is_guarded_by_try_except};

/// ## What it does
/// Checks for uses of deprecated Airflow symbols removed in Airflow X.Y.
///
/// ## Why is this bad?
/// These symbols were removed/moved in Airflow X.Y and will cause runtime errors.
///
/// ## Example / Use instead blocks...
#[derive(ViolationMetadata)]
#[violation_metadata(preview_since = "NEXT_RUFF_VERSION")]
pub(crate) struct MyMigrationRule {
    deprecated: String,
    replacement: String,
}

impl Violation for MyMigrationRule {
    const FIX_AVAILABILITY: FixAvailability = FixAvailability::Sometimes;

    #[derive_message_formats]
    fn message(&self) -> String {
        let MyMigrationRule { deprecated, replacement } = self;
        format!("`{deprecated}` is removed in Airflow X.Y; use `{replacement}` instead")
    }

    fn fix_title(&self) -> Option<String> {
        let MyMigrationRule { replacement, .. } = self;
        Some(format!("Use `{replacement}`"))
    }
}

pub(crate) fn my_migration_rule(checker: &Checker, expr: &Expr) {
    if !checker.semantic().seen_module(Modules::AIRFLOW) {
        return;
    }

    // Dispatch based on expression type:
    match expr {
        Expr::Attribute(ast::ExprAttribute { attr, .. }) => {
            check_name(checker, expr, attr.range());
        }
        Expr::Name(_) => {
            check_name(checker, expr, expr.range());
        }
        _ => {}
    }
}

fn check_name(checker: &Checker, expr: &Expr, ranged: TextRange) {
    let Some(qualified_name) = checker.semantic().resolve_qualified_name(expr) else {
        return;
    };

    let (replacement, module, name) = match qualified_name.segments() {
        ["airflow", "old_module", "OldName"] => (
            Replacement::Rename { module: "airflow.new_module", name: "NewName" },
            "airflow.old_module",
            "OldName",
        ),
        _ => return,
    };

    // Skip if guarded by try-except (conditional import):
    if is_guarded_by_try_except(expr, module, name, checker.semantic()) {
        return;
    }

    let mut diagnostic = checker.report_diagnostic(
        MyMigrationRule {
            deprecated: name.to_string(),
            replacement: replacement.to_string(),
        },
        ranged,
    );

    // Optionally generate a fix:
    // if let Some(fix) = generate_import_edit(...) {
    //     diagnostic.set_fix(fix);
    // }
}
```

### 3. Register the Rule Code

In `crates/ruff_linter/src/codes.rs`, add an entry under the `// airflow` section:

```rust
(Airflow, "xxx") => rules::airflow::rules::MyRuleName,
```

Keep the entries sorted by code number.

### 4. Export the Module

In `crates/ruff_linter/src/rules/airflow/rules/mod.rs`:
- Add `pub(crate) use my_rule_name::*;` in the use-declarations block (alphabetical order).
- Add `mod my_rule_name;` in the mod-declarations block (alphabetical order).

Do NOT add a duplicate module declaration in `crates/ruff_linter/src/rules/airflow/mod.rs` -- only `rules/mod.rs` needs it.

### 5. Add the Rule Dispatch

In `crates/ruff_linter/src/checkers/ast/analyze/`:
- For **statement-based** rules (function defs, assignments, class defs): add to `statement.rs`
- For **expression-based** rules (function calls, attribute access): add to `expression.rs`

Pattern:
```rust
if checker.is_rule_enabled(Rule::MyRuleName) {
    airflow::rules::my_rule_name(checker, node);
}
```

Place the dispatch near other airflow rule dispatches for consistency.

### 6. Create the Test Fixture

Create `crates/ruff_linter/resources/test/fixtures/airflow/AIRxxx.py`.

The fixture must include:
- Cases that SHOULD trigger the rule (with `# AIRxxx` comments)
- Cases that should NOT trigger the rule (edge cases, similar but valid patterns)
- For migration rules: cases guarded by try-except (should NOT trigger)

### 7. Add the Test Case

In `crates/ruff_linter/src/rules/airflow/mod.rs`, add a `#[test_case]` line:

```rust
#[test_case(Rule::MyRuleName, Path::new("AIRxxx.py"))]
```

Keep test cases sorted by rule code.

### 8. Format Code

**Always run `cargo fmt` before testing or committing.** Rust formatting issues (import ordering, closure formatting, method chain line breaks) will cause CI failures.

```sh
cargo fmt -p ruff_linter
```

### 9. Run Tests and Accept Snapshots

```sh
# Verify output manually first:
cargo run -p ruff -- check crates/ruff_linter/resources/test/fixtures/airflow/AIRxxx.py --no-cache --preview --select AIRxxx

# Run the test with RUFF_UPDATE_SCHEMA=1 to auto-update schemas (will fail first time, generating a snapshot):
RUFF_UPDATE_SCHEMA=1 cargo nextest run -p ruff_linter -- "airflow::tests"

# Accept the snapshot:
cargo insta accept

# Verify the test passes:
RUFF_UPDATE_SCHEMA=1 cargo nextest run -p ruff_linter -- "airflow::tests"
```

### 10. Regenerate Docs and Schemas

```sh
cargo dev generate-all
```

### 11. Run All Checks

```sh
cargo clippy -p ruff_linter --all-targets --all-features -- -D warnings
uvx prek run -a
```

### 12. Validate Against Airflow (if local repo available)

If the user provided a path to a local Airflow repository during pre-implementation, run the new rule against it to check for false positives:

```sh
cargo run -p ruff -- check <airflow_repo_path> --no-cache --preview --select AIRxxx
```

Review the output:
- **True positives**: Violations that correctly flag the anti-pattern. Report the count and sample locations.
- **False positives**: Violations that flag code that is actually correct. If found:
  1. Identify the pattern causing the false positive.
  2. Update the rule logic to exclude it (e.g., add a guard clause).
  3. Add the false-positive pattern as a non-violation test case in the fixture.
  4. Re-run steps 8–11 to update snapshots and verify.

Report findings to the user before finalizing.

## Shared Helpers (`helpers.rs`)

The `crates/ruff_linter/src/rules/airflow/helpers.rs` module provides shared utilities. Import from `crate::rules::airflow::helpers`.

### Replacement Enums

Used by migration rules to describe what replaces a deprecated symbol:

- **`Replacement`** — for builtin/SDK moves:
  - `None` — no replacement available
  - `Message(&'static str)` — custom message, no auto-fix
  - `AttrName(&'static str)` — attribute renamed (e.g., `dataset` to `asset`)
  - `Rename { module, name }` — moved to new module with new name
  - `SourceModuleMoved { module, name }` — module changed, name stays
  - `SourceModuleMovedToSDK { module, name, version }` — moved to SDK
  - `SourceModuleMovedWithMessage { module, name, message, suggest_fix }` — with custom message

- **`ProviderReplacement`** — for provider migrations (AIR302/312):
  - `Rename { module, name, provider, version }` — moved to provider with rename
  - `SourceModuleMovedToProvider { module, name, provider, version }` — module changed

- **`FunctionSignatureChange`** — for AIR303:
  - `Message(&'static str)` — describes the signature change

### Try-Except Guarding

Prevents false positives when symbols are conditionally imported:

```rust
use crate::rules::airflow::helpers::is_guarded_by_try_except;

// Skip if the usage is inside a try-except that catches ImportError/AttributeError
if is_guarded_by_try_except(expr, "airflow.old_module", "OldName", checker.semantic()) {
    return;
}
```

This checks whether the expression is in a try-except block that:
- For **imports**: catches `ImportError` or `ModuleNotFoundError`, and the try block imports from the new location
- For **attributes**: catches `AttributeError`, and the try block accesses the new attribute

### Fix Generation

```rust
use crate::rules::airflow::helpers::{generate_import_edit, generate_remove_and_runtime_import_edit};

// When symbol name changes (e.g., Dataset -> Asset):
if let Some(fix) = generate_import_edit(checker, stmt, "old_name", "new_module", "new_name") {
    diagnostic.set_fix(fix);  // Safe edit
}

// When module changes but name stays (provider migration):
if let Some(fix) = generate_remove_and_runtime_import_edit(checker, stmt, "new_module", "name") {
    diagnostic.set_fix(fix);  // Unsafe edit
}
```

### Class/Module Identification

```rust
use crate::rules::airflow::helpers::{is_airflow_builtin_or_provider, is_method_in_subclass};

// Check if qualified name matches airflow.<module>.**.*<suffix> or provider equivalent:
is_airflow_builtin_or_provider(segments, "operators", "Operator")
is_airflow_builtin_or_provider(segments, "secrets", "Backend")
is_airflow_builtin_or_provider(segments, "hooks", "Hook")

// Check if a method is defined in a subclass of a specific base:
is_method_in_subclass(function_def, semantic, "execute", |qn| {
    matches!(qn.segments(), ["airflow", "models" | "sdk", .., "BaseOperator"])
})
```

Note: `BaseOperator` task-execution-time methods include `execute`, `pre_execute`, and `post_execute`.
All three run at task execution time (not DAG parse time).

### Operator Argument Scope (`template_fields`)

Airflow operators declare a `template_fields` class attribute that determines which keyword arguments receive Jinja template rendering at runtime. This varies per operator (e.g., `BashOperator` templates `bash_command` and `env`; `PythonOperator` templates `op_args`, `op_kwargs`, `templates_dict`). When writing rules that inspect operator string arguments for template patterns, check **all** arguments (both positional and keyword) rather than restricting to known names — the pattern matching is typically specific enough to avoid false positives, and restricting to known names would miss custom operators and providers. Add a code comment explaining the rationale (see AIR201 for an example).

### Transitive Inheritance Checks

When checking if a class inherits from a base class, use `any_qualified_base_class` from `ruff_python_semantic::analyze::class` instead of directly iterating `class_def.bases()`. This handles transitive inheritance (e.g., `class A(BaseOperator) → class B(A) → class C(B)`):

```rust
use ruff_python_semantic::analyze::class::any_qualified_base_class;

any_qualified_base_class(class_def, semantic, &|qn| {
    matches!(qn.segments(), ["airflow", "models" | "sdk", .., "BaseOperator"])
})
```

### Detecting DAG Files

To check if a file is a Dag definition file, check for imports of `DAG` or `dag` from airflow. This is simpler and more reliable than checking for actual `DAG()` calls or `@dag` decorators, since types must be imported before use:

```rust
fn is_dag_file(semantic: &SemanticModel) -> bool {
    semantic.global_scope().binding_ids().any(|binding_id| {
        semantic
            .binding(binding_id)
            .as_any_import()
            .is_some_and(|import| {
                matches!(
                    import.qualified_name().segments(),
                    ["airflow", .., "DAG" | "dag"]
                )
            })
    })
}
```

### Scope-Based Context Detection

When determining whether code is at module level vs inside a function (e.g., to vary diagnostic messages), prefer `semantic.current_scope().kind` over `semantic.current_statements().any(...)`. The scope approach correctly handles nested classes inside functions:

```rust
let in_function = matches!(
    checker.semantic().current_scope().kind,
    ScopeKind::Function(_) | ScopeKind::Lambda(_)
);
```

`current_scope()` returns the **innermost** scope, so `Variable.get()` inside a class body nested in a function returns `ScopeKind::Class` (not function).

## Common Patterns

### Checking Decorators

**Important:** Before writing a new decorator-checking function, check if one already exists in `helpers.rs` (e.g., `is_airflow_task` in AIR301). If a decorator check is needed by multiple rules, extract it to `helpers.rs` as a shared utility.

Use `map_callable` to handle both `@decorator` and `@decorator()` forms:

```rust
use ruff_python_ast::helpers::map_callable;

fn has_some_decorator(function_def: &StmtFunctionDef, checker: &Checker) -> bool {
    function_def.decorator_list.iter().any(|decorator| {
        let expr = map_callable(&decorator.expression);
        checker
            .semantic()
            .resolve_qualified_name(expr)
            .is_some_and(|qn| matches!(qn.segments(), ["airflow", "decorators", "some_name"]))
    })
}
```

For rules targeting both Airflow 2 and 3, match both old and new decorator paths:

```rust
fn is_airflow_task(function_def: &StmtFunctionDef, semantic: &SemanticModel) -> bool {
    function_def.decorator_list.iter().any(|decorator| {
        semantic
            .resolve_qualified_name(map_callable(&decorator.expression))
            .is_some_and(|qn| matches!(qn.segments(),
                ["airflow", "decorators", "task"] | ["airflow", "sdk", "task"]
            ))
    })
}
```

For attribute-style decorators like `@task.branch`, check the `Expr::Attribute` and resolve the value part:

```rust
let expr = map_callable(&decorator.expression);
if let Expr::Attribute(ast::ExprAttribute { value, attr, .. }) = expr {
    if attr.as_str() == "branch" {
        checker.semantic().resolve_qualified_name(value)
            .is_some_and(|qn| matches!(qn.segments(), ["airflow", "decorators", "task"]))
    }
}
```

Also see `ruff_python_semantic::analyze::visibility` for generic decorator utilities: `is_staticmethod`, `is_classmethod`, `is_overload`, `is_abstract`, `is_property`, etc.

### Dual-Dispatch: Targeting Both TaskFlow and Operator APIs

When a rule must detect the same anti-pattern in both `@task.<variant>` decorated functions and operator callables (e.g., `BranchPythonOperator(python_callable=func)`), use this architecture:

1. **Shared analysis helper** — extract the core logic into a private function that operates on a function body:
```rust
fn could_be_short_circuit(body: &[Stmt]) -> bool { /* ... */ }
```

2. **Violation enum** — add a `Kind` enum to produce context-specific messages:
```rust
pub(crate) struct MyRule { kind: MyKind }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum MyKind { Decorator, Operator }
```

3. **Statement-level entry point** (for `@task.<variant>` decorators) — dispatched from `statement.rs` on `StmtFunctionDef`:
```rust
pub(crate) fn my_rule_decorator(checker: &Checker, function_def: &StmtFunctionDef) {
    // Check decorator, then call shared helper on function_def.body
}
```

4. **Expression-level entry point** (for operator calls) — dispatched from `expression.rs` on `ExprCall`. Resolve the `python_callable` argument to the function definition using the semantic model:
```rust
pub(crate) fn my_rule_operator(checker: &Checker, call: &ExprCall) {
    // 1. Resolve call.func to qualified name, match operator paths
    // 2. Extract python_callable keyword argument
    // 3. Resolve name to function definition:
    let Expr::Name(name_expr) = &keyword.value else { return; };
    let Some(binding_id) = semantic.only_binding(name_expr) else { return; };
    let BindingKind::FunctionDefinition(scope_id) = semantic.binding(binding_id).kind else { return; };
    let ScopeKind::Function(function_def) = semantic.scopes[scope_id].kind else { return; };
    // 4. Call shared helper on function_def.body
}
```

**Operator import paths to match** (example for `BranchPythonOperator`):
- `["airflow", "operators", "python", "BranchPythonOperator"]`
- `["airflow", "operators", "python_operator", "BranchPythonOperator"]` (legacy)
- `["airflow", "providers", "standard", "operators", "python", "BranchPythonOperator"]`

See AIR003 (`task_branch_as_short_circuit.rs`) for a complete working example.

### Checking Function Calls and Arguments

```rust
let Expr::Call(ast::ExprCall { func, arguments, .. }) = expr else { return; };

// Resolve the function being called:
checker
    .semantic()
    .resolve_qualified_name(func)
    .is_some_and(|qn| matches!(qn.segments(), ["airflow", .., "SomeClass"]))

// Check keyword arguments:
if let Some(keyword) = arguments.find_keyword("some_arg") {
    // keyword.value is the argument value expression
}
```

### Matching Airflow Operators (builtin + providers)

```rust
match qualified_name.segments() {
    // Builtin operators
    ["airflow", "operators", ..] => true,
    // Provider operators (operators must appear somewhere in the middle)
    ["airflow", "providers", rest @ ..] => {
        rest.iter().position(|&s| s == "operators")
            .is_some_and(|pos| pos + 1 < rest.len())
    }
    _ => false,
}
```

### Collecting Return Statements (recursive)

Use `ReturnStatementVisitor` to find all returns including those in nested blocks:

```rust
use ruff_python_ast::helpers::ReturnStatementVisitor;
use ruff_python_ast::visitor::Visitor;

let mut visitor = ReturnStatementVisitor::default();
for stmt in &function_def.body {
    visitor.visit_stmt(stmt);
}
let returns = &visitor.returns;
```

### Expression Type Dispatching (migration rules)

Migration rules typically dispatch on expression type:

```rust
match expr {
    Expr::Call(ast::ExprCall { func, arguments, .. }) => {
        check_call_arguments(checker, func, arguments);
    }
    Expr::Attribute(ast::ExprAttribute { attr, .. }) => {
        check_name(checker, expr, attr.range());
    }
    Expr::Name(_) => {
        check_name(checker, expr, expr.range());
    }
    Expr::Subscript(ast::ExprSubscript { value, slice, .. }) => {
        check_subscript_access(checker, value, slice);
    }
    _ => {}
}
```

### Violations with Dynamic Fields

For migration rules, use struct fields to parameterize messages:

```rust
pub(crate) struct MyRule {
    deprecated: String,
    replacement: String,
}

impl Violation for MyRule {
    const FIX_AVAILABILITY: FixAvailability = FixAvailability::Sometimes;

    #[derive_message_formats]
    fn message(&self) -> String {
        let MyRule { deprecated, replacement } = self;
        format!("`{deprecated}` is removed; use `{replacement}`")
    }

    fn fix_title(&self) -> Option<String> {
        let MyRule { replacement, .. } = self;
        Some(format!("Use `{replacement}`"))
    }
}
```

### Function ordering

When adding new helper functions or methods, place the higher-level predicates or public-facing helpers above the lower-level utilities they call. That way reviewers see the intent/entry point first, followed by the supporting helpers (e.g., `in_airflow_task_function` before `is_airflow_task`).

### Mixed-content string scanning

When a rule must detect a pattern **within** a string argument — not just recognize the string's overall structure — use a raw-source scanner rather than operating on `to_str()`. This handles all quote styles (single, double, triple) uniformly and produces accurate sub-range `TextRange` values for in-place fixes.

**When to use**: the pattern appears inside a larger Jinja template or shell command string that has surrounding content (e.g., `"echo {{ ti.xcom_pull('task') }}"`). The fix should replace only the detected sub-expression, not the entire string argument.

**Pattern** (from AIR201):

```rust
use ruff_text_size::TextSize;

struct MyMatch {
    start: TextSize, // absolute file position of match start
    end: TextSize,   // absolute file position just past match end
    // ... extracted fields ...
}

fn scan_my_patterns(source: &str, literal_start: TextSize) -> Vec<MyMatch> {
    let mut matches = Vec::new();
    let mut pos = 0;

    while pos < source.len() {
        let remaining = &source[pos..];
        let mut cursor = Cursor::new(remaining);

        // Try to match at this position; on mismatch, advance by one byte.
        let Some(token) = parse_identifier(&mut cursor) else {
            pos += 1;
            continue;
        };
        if token != "expected_receiver" {
            pos += token.len(); // skip entire identifier to avoid suffix re-matches
            continue;
        }

        // ... parse rest of pattern using eat_char, parse_identifier, etc. ...

        let consumed = remaining.len() - cursor.as_str().len();

        if let (Ok(s), Ok(e)) = (u32::try_from(pos), u32::try_from(pos + consumed)) {
            matches.push(MyMatch {
                start: literal_start + TextSize::new(s),
                end: literal_start + TextSize::new(e),
                // ...
            });
            pos += consumed;
            continue;
        }
        pos += 1;
    }
    matches
}
```

**In the rule function**:

```rust
// Pure-template path first (entire string is the expression):
if let Some(result) = parse_pure_template(string_value) {
    // whole-argument replacement fix
    continue;
}

// Mixed-content path: pattern appears within larger string
let raw_source = checker.locator().slice(string_literal.range());
for m in scan_my_patterns(raw_source, string_literal.start()) {
    let mut diagnostic = checker.report_diagnostic(MyViolation { .. }, arg_value.range());
    if in_scope {
        diagnostic.set_fix(Fix::unsafe_edit(Edit::range_replacement(
            "replacement_text".to_string(),
            TextRange::new(m.start, m.end),
        )));
    }
}
```

**Key invariants**:
- `checker.locator().slice(string_literal.range())` returns the raw source starting at `string_literal.start()`, so adding a within-source byte offset to `string_literal.start()` gives the correct absolute `TextRange`.
- The scanner is quote-agnostic: the target pattern cannot appear in `"`, `'`, or `"""` quote characters.
- Advancing `pos += token.len()` (not just `pos += 1`) when a non-matching identifier is found prevents false positives from identifier suffixes (e.g., `multi_ti` matching as `ti`).
- Store `TextSize` in the match struct (not `usize`) and use `u32::try_from` to convert — avoids `as u32` cast truncation lint.
- Multiple matches in one string each get their own `Fix` with `IsolationLevel::NonOverlapping` (the default), which ruff applies in a single pass when ranges do not overlap.

See `crates/ruff_linter/src/rules/airflow/rules/xcom_pull_in_template_string.rs` (`scan_xcom_pull_patterns`) for a complete working example.

## Documentation Guidelines

Rule documentation (the doc comments in the rule struct) must follow these conventions:

### Structure

Use this exact section order (include only sections that apply):

1. **`## What it does`** (required) — One-line description of what the rule checks for
2. **`## Why is this bad?`** (required) — Explanation of why the pattern is problematic
3. **`## Example`** (required) — Python code that triggers the violation
4. **`Use instead:`** (required) — Corrected Python code
5. **`## Fix safety`** (optional) — Notes about fix edge cases or when fixes might be unsafe
6. **`## Options`** (optional) — Configuration settings that affect the rule
7. **`## References`** (optional) — Links to external documentation

### Terminology

- **Dag (capitalization)**:
  - Use `DAG` when referring to the class: "The `DAG()` constructor..."
  - Use `@dag` when referring to the decorator: "Functions decorated with `@dag`..."
  - Use "Dag" (proper noun, no backticks) when referring to a workflow as a general concept: "If your Dag does not have...", "the serialized Dag hash"
  
- **Task terminology**:
  - Use `@task` for the decorator
  - Use "task" (lowercase, no backticks) for the general concept
  - Use specific operator names in backticks: `PythonOperator`, `BranchPythonOperator`

- **Airflow versions**: Write as "Airflow 2", "Airflow 3", "Airflow 3.0", "Airflow 3.1" (capitalize, no backticks)

- **Code references**: Always use backticks for:
  - Class names: `DAG`, `BaseOperator`
  - Function/method names: `execute()`, `datetime.now()`
  - Decorators: `@dag()`, `@task.branch`
  - Parameters/arguments: `schedule`, `task_id`, `python_callable`
  - Module paths: `airflow.operators.python`, `airflow.sdk`
  - String literals in explanations: `` `"schedule"` ``

### Style Guidelines

- **Conciseness**: Keep "What it does" to one sentence. Expand details in "Why is this bad?"
- **Active voice**: Prefer "Using X causes..." over "X may cause..." or "It is possible that X causes..."
- **Imperative starts**: Begin sentences in "Why is this bad?" with action verbs: "Using...", "This leads to...", "These symbols were removed..."
- **Specific consequences**: Don't just say "this is bad practice"—explain the actual impact (performance, compatibility, maintainability)
- **Code examples**: Keep them minimal but complete enough to demonstrate the issue. Include necessary imports.

### Message Guidelines

Error messages (the `message()` method) should:
- Be a **generic description** of the problem — do NOT include context-specific suggestions in the message
- Use backticks around code symbols: `` "`{deprecated}` is removed in Airflow 3.0" ``
- Avoid starting with "Checks for" or "Detects" (this is for documentation, not messages)

Fix titles (the `fix_title()` method) should:
- Contain context-specific **suggestions** (e.g., "Use Jinja templates" vs "Move into a `@task`-decorated function")
- Start with an imperative verb: "Use `schedule`", "Replace with...", "Remove..."
- Be very brief (2-5 words when possible)
- Even without an actual auto-fix, `fix_title()` is displayed as a separate `help: ...` line in diagnostics

**Pattern: Generic message + context-specific fix title** (from AIR003):
```rust
fn message(&self) -> String {
    "`Variable.get()` outside of a task".to_string()  // Generic
}

fn fix_title(&self) -> Option<String> {
    if self.in_function {
        Some("Move into a `@task`-decorated function".to_string())  // Context-specific
    } else {
        Some("Use Jinja templates instead".to_string())  // Context-specific
    }
}
```

### Examples from Existing Rules

Good documentation structure (from AIR002):
```rust
/// ## What it does
/// Checks for a `DAG()` class or `@dag()` decorator without an explicit
/// `schedule` parameter.
///
/// ## Why is this bad?
/// The default value of the `schedule` parameter on Airflow 2 is
/// `timedelta(days=1)`, which is almost never what a user is looking for.
/// Airflow 3 changed the default value to `None`, which would break
/// existing Dags using the implicit default.
///
/// ## Example
/// ```python
/// from airflow import DAG
///
/// # Using the implicit default schedule.
/// dag = DAG(dag_id="my_dag")
/// ```
///
/// Use instead:
/// ```python
/// from datetime import timedelta
/// from airflow import DAG
///
/// dag = DAG(dag_id="my_dag", schedule=timedelta(days=1))
/// ```
```

Note the use of:
- "Dag" (proper noun) in prose: "would break existing Dags"
- `` `DAG()` `` and `` `@dag()` `` for class and decorator
- Backticks for parameters: `` `schedule` ``, `` `timedelta(days=1)` ``
- "Airflow 2" and "Airflow 3" (capitalized, no backticks)

## Key Conventions

- Use `checker.report_diagnostic(ViolationStruct, range)` — NOT `Diagnostic::new()`.
- Add `#[violation_metadata(preview_since = "NEXT_RUFF_VERSION")]` for new rules.
- Always guard with `checker.semantic().seen_module(Modules::AIRFLOW)`.
- For migration rules, use `is_guarded_by_try_except` to avoid false positives on conditional imports.
- For rules targeting both Airflow 2 and 3, match both old and new (`airflow.sdk`) import paths (see mapping table above).
- **Reuse over duplication:** Before writing a utility function, search `ruff_python_semantic`, `ruff_python_ast`, and `airflow/helpers.rs` for existing implementations. If a pattern is useful in multiple rules, add it to `helpers.rs` rather than keeping it local to one rule.
- Follow early-return style (guard clauses) rather than deeply nested if-let chains.
- Prefer let chains (`if let` combined with `&&`) over nested `if let` when possible.
- Avoid `panic!`, `unreachable!`, or `.unwrap()`.
- Use `#[expect()]` over `#[allow()]` for suppressing clippy lints.
- For internal (non-public) functions, implementation notes (e.g., "this is similar to X but can't reuse it because...") should be `///` doc comments, not `//` comments.
