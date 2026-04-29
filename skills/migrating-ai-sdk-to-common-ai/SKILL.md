---
name: migrating-ai-sdk-to-common-ai
description: Migrates Airflow projects from airflow-ai-sdk to apache-airflow-providers-common-ai 0.1.0+. Use this skill when the user wants to replace airflow-ai-sdk with the official Airflow AI provider, migrate LLM decorators (@task.llm, @task.agent, @task.llm_branch, @task.embed), switch from model strings/objects to connection-based LLM configuration, or update imports from airflow_ai_sdk to the new provider. Also trigger when the user mentions common-ai provider, AIP-99, pydanticai connection, or migrating away from airflow-ai-sdk.
---

# Migrate airflow-ai-sdk to apache-airflow-providers-common-ai

This skill migrates Airflow projects from `airflow-ai-sdk` to `apache-airflow-providers-common-ai` (0.1.0+), the official Airflow AI provider built on PydanticAI.

> **CRITICAL**: The new provider requires **Airflow 3.0+** and **pydantic-ai-slim >= 1.34.0**. The API surface has changed: LLM configuration moves from code (model strings/objects) to Airflow connections (`pydanticai` type). There is no `@task.embed` in the new provider.

## Before starting

Use the Grep tool with the pattern below to inventory everything that needs to migrate:

```
airflow_ai_sdk|airflow-ai-sdk|ai_sdk|@task\.llm|@task\.agent|@task\.llm_branch|@task\.embed
```

From the results, capture:

1. All files importing `airflow-ai-sdk` / `airflow_ai_sdk`
2. Which decorators are in use: `@task.llm`, `@task.agent`, `@task.llm_branch`, `@task.embed`
3. The model configuration pattern (string names like `"gpt-5"`, or `OpenAIModel(...)` objects)
4. Any `airflow_ai_sdk.BaseModel` subclasses used as `output_type`

Use this inventory to drive the steps below.

---

## Step 1: Update requirements.txt

**Remove:**
```
airflow-ai-sdk[openai]
# or any variant: airflow-ai-sdk[openai]==0.1.7, airflow-ai-sdk[anthropic], etc.
```

**Add:**
```
apache-airflow-providers-common-ai[openai]>=0.1.0
```

Use the latest available 0.x version unless the user has pinned a specific one. Available extras match the LLM provider: `[openai]`, `[anthropic]`, `[google]`, `[bedrock]`, `[groq]`, `[mistral]`, `[mcp]`.

Keep `sentence-transformers` and `torch` if the project uses embeddings (they now run via plain `@task` instead of `@task.embed`).

---

## Step 2: Create PydanticAI connection

The new provider uses an Airflow connection instead of model strings or objects in code.

**Connection type:** `pydanticai`
**Default connection ID:** `pydanticai_default`

### Via environment variable (.env)

```bash
AIRFLOW_CONN_PYDANTICAI_DEFAULT='{
    "conn_type": "pydanticai",
    "password": "<api-key>",
    "extra": {
        "model": "<provider>:<model-name>"
    }
}'
```

### Model format

The model field uses `provider:model` format:

| Provider | Example model value |
|----------|-------------------|
| OpenAI | `openai:gpt-5` |
| Anthropic | `anthropic:claude-sonnet-4-20250514` |
| Google | `google:gemini-2.5-pro` |
| Groq | `groq:llama-3.3-70b-versatile` |
| Mistral | `mistral:mistral-large-latest` |
| Bedrock | `bedrock:us.anthropic.claude-sonnet-4-20250514-v1:0` |

### Custom endpoints (Ollama, vLLM, Snowflake Cortex, etc.)

Set `host` to the base URL:
```bash
AIRFLOW_CONN_PYDANTICAI_CORTEX='{
    "conn_type": "pydanticai",
    "password": "<api-key>",
    "host": "https://my-endpoint.com/v1",
    "extra": {
        "model": "openai:<model-name>"
    }
}'
```

Use the `openai:` prefix for any OpenAI-compatible API, regardless of the actual provider.

### Connection ID convention

The env var name determines the connection ID:
- `AIRFLOW_CONN_PYDANTICAI_DEFAULT` creates `pydanticai_default`
- `AIRFLOW_CONN_PYDANTICAI_CORTEX` creates `pydanticai_cortex`

### Model resolution priority

1. `model_id` parameter on the decorator/operator (highest)
2. `model` in connection's extra JSON (fallback)

---

## Step 3: Migrate decorators

### @task.llm

```python
# BEFORE (airflow-ai-sdk)
import airflow_ai_sdk as ai_sdk

class MyOutput(ai_sdk.BaseModel):
    field: str

@task.llm(
    model="gpt-5",                    # or model=OpenAIModel(...)
    system_prompt="You are helpful.",
    output_type=MyOutput,
)
def my_task(text: str) -> str:
    return text

# AFTER (apache-airflow-providers-common-ai)
from pydantic import BaseModel

class MyOutput(BaseModel):
    field: str

@task.llm(
    llm_conn_id="pydanticai_default",  # Airflow connection ID
    system_prompt="You are helpful.",
    output_type=MyOutput,
)
def my_task(text: str) -> str:
    return text
```

**Parameter mapping:**

| airflow-ai-sdk | common-ai provider | Notes |
|----------------|-------------------|-------|
| `model="gpt-5"` | `llm_conn_id="pydanticai_default"` | Model specified in connection |
| `model=OpenAIModel(...)` | `llm_conn_id="pydanticai_default"` | Model + endpoint in connection |
| `system_prompt="..."` | `system_prompt="..."` | Unchanged |
| `output_type=MyModel` | `output_type=MyModel` | Unchanged |
| `result_type=MyModel` | `output_type=MyModel` | `result_type` was already deprecated |
| (not available) | `model_id="openai:gpt-5"` | Override connection's model |
| (not available) | `require_approval=True` | Built-in HITL review |
| (not available) | `agent_params={...}` | Extra kwargs for pydantic-ai Agent |

### @task.llm_branch

```python
# BEFORE
@task.llm_branch(
    model="gpt-5",
    system_prompt="Choose a team...",
    allow_multiple_branches=False,
)
def route(text: str) -> str:
    return text

# AFTER
@task.llm_branch(
    llm_conn_id="pydanticai_default",
    system_prompt="Choose a team...",
    allow_multiple_branches=False,    # same parameter, unchanged
)
def route(text: str) -> str:
    return text
```

Only change: `model=` becomes `llm_conn_id=`.

### @task.agent

This has the biggest API change. The Agent is no longer pre-built in user code.

```python
# BEFORE (airflow-ai-sdk) - Agent built at module level
from pydantic_ai import Agent

my_agent = Agent(
    "gpt-5",
    system_prompt="You are a research assistant.",
    tools=[search_tool, lookup_tool],
)

@task.agent(agent=my_agent)
def research(question: str) -> str:
    return question

# AFTER (common-ai provider) - No Agent object, config via parameters
@task.agent(
    llm_conn_id="pydanticai_default",
    system_prompt="You are a research assistant.",
    agent_params={"tools": [search_tool, lookup_tool]},
)
def research(question: str) -> str:
    return question
```

**Parameter mapping:**

| airflow-ai-sdk | common-ai provider | Notes |
|----------------|-------------------|-------|
| `agent=Agent(model, ...)` | `llm_conn_id="..."` | Model from connection |
| Agent's `system_prompt` | `system_prompt="..."` | Now a decorator param |
| Agent's `tools=[...]` | `agent_params={"tools": [...]}` | Tools via agent_params dict |
| Agent's `output_type` | `output_type=MyModel` | Now a decorator param |
| (not available) | `toolsets=[...]` | pydantic-ai 1.x Toolset objects |
| (not available) | `durable=True` | Step-level caching |
| (not available) | `enable_hitl_review=True` | Iterative human review loop |

**Key insight:** Everything that was configured on the `Agent()` constructor now goes into either a top-level decorator parameter or `agent_params`. The `agent_params` dict is passed directly to pydantic-ai's `Agent` constructor.

### @task.embed (NO EQUIVALENT)

The new provider does NOT include an embed decorator. Replace with a plain `@task`:

```python
# BEFORE (airflow-ai-sdk)
@task.embed(
    model_name="all-MiniLM-L6-v2",
    encode_kwargs={"normalize_embeddings": True},
    max_active_tis_per_dagrun=1,
)
def embed_text(text: str) -> str:
    return text

# AFTER (plain @task with sentence-transformers)
@task(max_active_tis_per_dagrun=1)
def embed_text(text: str) -> list[float]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(text, normalize_embeddings=True).tolist()
```

Note: The model is loaded on each task execution. For small workloads this is fine. For large batches, consider embedding all texts in a single task instead of using `.expand()`.

---

## Step 4: Update imports

| Old import | New import |
|-----------|-----------|
| `import airflow_ai_sdk as ai_sdk` | Remove entirely |
| `from airflow_ai_sdk import BaseModel` | `from pydantic import BaseModel` |
| `from airflow_ai_sdk.models.base import BaseModel` | `from pydantic import BaseModel` |
| `class Foo(ai_sdk.BaseModel):` | `class Foo(BaseModel):` |
| `from pydantic_ai import Agent` | Remove if Agent was only used for `@task.agent` |
| `from pydantic_ai.models.openai import OpenAIModel` | Remove (model config in connection now) |

The `@task.llm`, `@task.agent`, `@task.llm_branch` decorators are auto-registered by the provider. No explicit import needed beyond `from airflow.sdk import task`.

`pydantic_ai` imports for non-decorator usage (e.g., `BinaryContent` for multimodal) are still valid since the new provider depends on `pydantic-ai-slim>=1.34.0`.

---

## Step 5: Update connections.yaml (if used for local testing)

```yaml
pydanticai_default:
  conn_type: pydanticai
  password: <api-key>
  extra:
    model: "openai:gpt-5"
```

For custom endpoints:
```yaml
pydanticai_cortex:
  conn_type: pydanticai
  password: <api-key>
  host: https://my-endpoint.com/v1
  extra:
    model: "openai:llama3.1-8b"
```

---

## Step 6: Clean up env vars

The new provider reads model config from the `pydanticai` connection, so env vars that previously fed the model in code are usually redundant. Before removing any of them, grep the project (and any sibling scripts/services) to confirm nothing else still references them:

```
OPENAI_API_KEY|OPENAI_BASE_URL|ANTHROPIC_API_KEY|GOOGLE_API_KEY
```

Candidates for removal **only if no other code references them**:
- `OPENAI_API_KEY` (now in the pydanticai connection's password field)
- `OPENAI_BASE_URL` (now in the connection's host field)
- Custom model name vars (now in the connection's extra.model)

If anything outside the migrated DAGs still uses them (other DAGs not yet migrated, helper scripts, non-Airflow services sharing the `.env`), leave them in place.

**Keep** `AIRFLOW_CONN_*` env vars for all connections.

---

## Step 7: Verify

After migration, grep the codebase to confirm no stale references remain:

```
airflow_ai_sdk|airflow-ai-sdk|ai_sdk\.BaseModel|from pydantic_ai import Agent|from pydantic_ai.models
```

Verify:
- [ ] No imports from `airflow_ai_sdk`
- [ ] No `Agent()` objects created for `@task.agent` (unless used outside decorators)
- [ ] No `model=` parameter on LLM decorators (should be `llm_conn_id=`)
- [ ] All `@task.embed` replaced with plain `@task`
- [ ] `pydanticai` connection configured in `.env` or connections.yaml
- [ ] `requirements.txt` has `apache-airflow-providers-common-ai[...]` instead of `airflow-ai-sdk[...]`

---

## Quick reference: New features in common-ai provider

These features are available after migration but have no airflow-ai-sdk equivalent:

| Feature | Parameter | Description |
|---------|-----------|-------------|
| HITL approval | `require_approval=True` on `@task.llm` | Pause for human review before returning |
| HITL review loop | `enable_hitl_review=True` on `@task.agent` | Iterative review with regeneration |
| Durable execution | `durable=True` on `@task.agent` | Step-level caching for resilience |
| Tool logging | `enable_tool_logging=True` on `@task.agent` | INFO-level tool call logs (default: on) |
| Model override | `model_id="openai:gpt-5"` | Override connection's model per-task |
| File analysis | `@task.llm_file_analysis` | Analyze files/images via ObjectStoragePath |
| NL-to-SQL | `@task.llm_sql` | Generate SQL from natural language |
