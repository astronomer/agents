---
name: migrating-ai-sdk-to-common-ai
description: Migrates Airflow projects from airflow-ai-sdk to apache-airflow-providers-common-ai 0.4.0+. Use when replacing airflow-ai-sdk with the official Airflow AI provider - migrating LLM decorators (@task.llm, @task.agent, @task.llm_branch, @task.embed), switching from model strings/objects to connection-based LLM configuration, updating imports from airflow_ai_sdk to the new provider, or upgrading an existing common-ai 0.1.x setup to 0.4.x (multimodal prompts, toolsets, embedding operators); also when common-ai provider, AIP-99, a pydanticai connection or migrating away from airflow-ai-sdk come up.
---

# Migrate airflow-ai-sdk to apache-airflow-providers-common-ai

This skill migrates Airflow projects from `airflow-ai-sdk` to `apache-airflow-providers-common-ai` (target **0.4.0+**), the official Airflow AI provider built on PydanticAI. It also covers upgrading projects already on common-ai 0.1.x, since several capabilities (multimodal prompts, `toolsets`, embedding operators, structured-output XCom behavior) changed between 0.1.0 and 0.4.0.

> **CRITICAL**: The new provider requires **Airflow 3.0+** and (for 0.4.0) **pydantic-ai-slim >= 1.71.0**. The API surface has changed: LLM configuration moves from code (model strings/objects) to Airflow connections (`pydanticai` type). There is no `@task.embed` in the new provider; embeddings move to the LlamaIndex integration or a plain `@task` (see Step 3).

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
apache-airflow-providers-common-ai[openai]>=0.4.0
```

Use the latest available 0.x version unless the user has pinned a specific one. Available extras (0.4.0): `[openai]`, `[anthropic]`, `[google]`, `[bedrock]`, `[llamaindex]`, `[langchain]`, `[mcp]`, plus file-format extras (`[pdf]`, `[docx]`, `[parquet]`, `[avro]`) for `DocumentLoaderOperator` and `[sql]`/`[common-sql]` for the SQL operators. There are no `[groq]`/`[mistral]` extras; for those providers install the matching `pydantic-ai-slim` extra yourself.

Add `[llamaindex]` if the project migrates `@task.embed` to the `LlamaIndexEmbeddingOperator` (recommended, see Step 3). In that case `sentence-transformers` and `torch` can usually be **removed**, which shrinks the image considerably. Keep them only if the project stays on local sentence-transformers embeddings via plain `@task`.

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

### Other connection types (0.4.0)

Besides `pydanticai`, the provider registers vendor-specific connection types: `pydanticai-azure` (Azure OpenAI: host = endpoint, extra `api_version`), `pydanticai-bedrock` (AWS credentials/region in extra), and `pydanticai-vertex` (GCP project/location in extra). The LlamaIndex and LangChain hooks read API key/host/extra from whatever connection ID they are given, so a single `pydanticai_default` connection can serve LLM calls **and** embeddings: one API key entry for the whole project.

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
| (not available) | `serialize_output=True` | Force dict shape for BaseModel output |

**Multimodal prompts (0.4.0+):** the translation function may return a `Sequence[UserContent]` instead of a string, e.g. for vision:

```python
@task.llm(llm_conn_id="pydanticai_default", system_prompt="...", output_type=ReviewAnalysis)
def analyze(text: str, image_path: str | None = None):
    if image_path:
        with open(image_path, "rb") as f:
            return [text, BinaryContent(data=f.read(), media_type="image/jpeg")]
    return text
```

This matches the old airflow-ai-sdk vision pattern, so vision code migrates unchanged. Note: common-ai **0.1.x only accepted strings** — if a project disabled vision to migrate to 0.1.0, re-enable it when bumping to 0.4.0. Non-string prompts are incompatible with `require_approval=True` / `enable_hitl_review=True` (both render the prompt as text).

**Structured output via XCom (0.4.0 behavior change):** with `output_type=<BaseModel subclass>`, the model **instance** flows through XCom on Airflow cores whose task SDK has `SUPPORTS_OPERATOR_DESERIALIZATION_WALKER` (attribute access downstream); on older cores (including Astro Runtime 3.2 task SDK 1.2.x) the provider automatically dumps to a **dict** (subscript access). Check which shape arrives at runtime before choosing attribute vs dict access downstream, or set `serialize_output=True` to force the dict shape everywhere. The `output_type` class must be defined at **module scope** (nested classes cannot be deserialized from XCom).

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
from pydantic_ai.toolsets import FunctionToolset

@task.agent(
    llm_conn_id="pydanticai_default",
    system_prompt="You are a research assistant.",
    toolsets=[FunctionToolset(tools=[search_tool, lookup_tool])],
)
def research(question: str) -> str:
    return question
```

**Parameter mapping:**

| airflow-ai-sdk | common-ai provider | Notes |
|----------------|-------------------|-------|
| `agent=Agent(model, ...)` | `llm_conn_id="..."` | Model from connection |
| Agent's `system_prompt` | `system_prompt="..."` | Now a decorator param |
| Agent's `tools=[...]` | `toolsets=[FunctionToolset(tools=[...])]` | Preferred: gets automatic tool-call logging |
| Agent's `tools=[...]` | `agent_params={"tools": [...]}` | Also works, but no tool-call logging |
| Agent's `output_type` | `output_type=MyModel` | Now a decorator param |
| (not available) | `durable=True` | Step-level caching (needs `[common.ai] durable_cache_path`) |
| (not available) | `enable_hitl_review=True` | Iterative human review loop (see below) |

**Key insight:** Everything that was configured on the `Agent()` constructor now goes into either a top-level decorator parameter or `agent_params`. The `agent_params` dict is passed directly to pydantic-ai's `Agent` constructor. Prefer `toolsets` over `agent_params["tools"]`: the operator wraps each toolset in a `LoggingToolset`, so every tool call appears in the task log with timing.

**enable_hitl_review behavior:** the task generates a first draft, then **blocks** until a human acts. The reviewer uses the **HITL Review** tab/extra link on the task instance (chat UI from the provider's auto-registered `hitl_review` plugin) to request changes (agent regenerates with the feedback in its message history) or approve. Constraints: requires a string prompt, incompatible with `durable=True`, and the final (possibly regenerated) output is what flows to XCom. Warn users that the Dag run waits indefinitely at this task unless `hitl_timeout` is set. For headless testing, the plugin exposes REST endpoints under `/hitl-review`: `GET /sessions/find`, `POST /sessions/feedback`, `POST /sessions/approve`, `POST /sessions/reject` (query params `dag_id`, `task_id`, `run_id`, `map_index`).

### @task.embed (NO EQUIVALENT — three replacement options)

The new provider does NOT include an embed decorator. Pick the replacement based on what the project needs:

**Option A (recommended): `LlamaIndexEmbeddingOperator`** (0.4.0, `[llamaindex]` extra). Connection-based, one task embeds the whole document list, and with `persist_dir` the resulting vector index is persisted for retrieval (pairs with `LlamaIndexRetrievalOperator`):

```python
from airflow.providers.common.ai.operators.llamaindex_embedding import LlamaIndexEmbeddingOperator

_embeddings = LlamaIndexEmbeddingOperator(
    task_id="create_embeddings",
    documents=[{"text": "...", "metadata": {"id": 1}}, ...],  # templated, accepts XComArg
    llm_conn_id="pydanticai_default",   # reuses the same connection (API key only)
    embed_model="text-embedding-3-small",
    persist_dir=f"{AIRFLOW_HOME}/include/my_index",  # optional; local path or s3://, gs://, ...
)
```

The operator returns `{"chunks": [{"text", "metadata", "vector"}], ...}`. Put a stable key into each document's `metadata` — it round-trips through chunking, so vectors can be mapped back to source records.

**Option B: `LlamaIndexHook` for raw vectors** (no operator, no persisted index). Shortest path when vectors go straight to a database:

```python
@task
def create_embeddings(rows):
    from airflow.providers.common.ai.hooks.llamaindex import LlamaIndexHook
    embed_model = LlamaIndexHook(
        llm_conn_id="pydanticai_default",
        embed_model="text-embedding-3-small",
    ).get_embedding_model()
    vectors = embed_model.get_text_embedding_batch([r["text"] for r in rows])
    return list(zip([r["id"] for r in rows], vectors))
```

**Option C: plain `@task` with sentence-transformers** (keeps the old local/offline behavior, no API cost; requires keeping `sentence-transformers` + `torch` in requirements):

```python
@task
def embed_texts(texts: list[str]) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(texts, normalize_embeddings=True).tolist()
```

Note on dimensions: switching from `all-MiniLM-L6-v2` (384) to `text-embedding-3-small` (1536) changes vector size — existing stored embeddings must be regenerated, and fixed-size vector columns (e.g. pgvector `vector(384)`) need a schema change. Embed all texts in one task/batch call rather than `.expand()` per text: batching is one API round-trip and avoids per-task model loading.

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
| (new) | `from pydantic_ai.toolsets import FunctionToolset` for `@task.agent` toolsets |

The `@task.llm`, `@task.agent`, `@task.llm_branch` decorators are auto-registered by the provider. No explicit import needed beyond `from airflow.sdk import task`.

`pydantic_ai` imports for non-decorator usage (e.g., `BinaryContent` for multimodal) are still valid since the new provider depends on `pydantic-ai-slim` (>= 1.71.0 for provider 0.4.0).

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
- [ ] All `@task.embed` replaced (LlamaIndex operator/hook or plain `@task`); stored embeddings regenerated if the model/dimensions changed
- [ ] Vision translation functions return `[text, BinaryContent(...)]` again if they were string-only-restricted under common-ai 0.1.x
- [ ] Downstream consumers of `output_type=BaseModel` results use the XCom shape that actually arrives (dict on older cores, instance on newer; `serialize_output=True` pins it)
- [ ] `pydanticai` connection configured in `.env` or connections.yaml
- [ ] `requirements.txt` has `apache-airflow-providers-common-ai[...]` instead of `airflow-ai-sdk[...]`; `torch`/`sentence-transformers` removed if no longer used
- [ ] Run the Dags end-to-end: tasks with `enable_hitl_review=True` or `require_approval=True` wait for human input, so the test plan must include acting on them (UI tab or `/hitl-review` REST)

---

## Quick reference: New features in common-ai provider

These features are available after migration but have no airflow-ai-sdk equivalent:

| Feature | Parameter / API | Since | Description |
|---------|-----------------|-------|-------------|
| HITL approval | `require_approval=True` on `@task.llm` | 0.1.0 | Pause for human review before returning |
| HITL review loop | `enable_hitl_review=True` on `@task.agent` | 0.1.0 | Iterative review with regeneration (chat UI via `hitl_review` plugin) |
| Durable execution | `durable=True` on `@task.agent` | 0.1.0 | Step-level caching for resilience |
| Tool logging | `enable_tool_logging=True` on `@task.agent` | 0.1.0 | INFO-level tool call logs (default: on; requires `toolsets`) |
| Model override | `model_id="openai:gpt-5"` | 0.1.0 | Override connection's model per-task |
| File analysis | `@task.llm_file_analysis` | 0.1.0 | Analyze files/images via ObjectStoragePath |
| NL-to-SQL | `@task.llm_sql` | 0.1.0 | Generate SQL from natural language |
| Multimodal prompts | Translation function returns `Sequence[UserContent]` | 0.4.0 | Vision and other binary content in `@task.llm` / `@task.agent` / `@task.llm_branch` |
| Pydantic instance via XCom | `output_type=BaseModel` (with `serialize_output` opt-out) | 0.4.0 | Instance flows through XCom on capable cores; dict fallback otherwise |
| Embeddings | `LlamaIndexEmbeddingOperator` (+ `persist_dir`) | 0.4.0 | Connection-based embeddings + persisted vector index |
| Retrieval | `LlamaIndexRetrievalOperator` | 0.4.0 | Top-k similarity search over a persisted index |
