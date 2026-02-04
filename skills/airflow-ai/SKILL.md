---
name: airflow-ai
description: Use when the user wants to call an LLM, run an AI agent, generate embeddings, or implement GenAI patterns in Airflow using the Airflow AI SDK. Covers `@task.llm`, `@task.agent`, `@task.embed`, `@task.llm_branch`, plus advanced patterns like RAG, prompt-chaining, multi-agent orchestration, and batch inference. Before implementing, verify model provider, decorator type, and output structure. Does not cover human-in-the-loop workflows (see airflow-hitl).
---

# Airflow AI SDK

Integrate LLMs, AI agents, and embeddings into Airflow DAGs using the Airflow AI SDK's task decorators. This skill covers decorator selection, provider configuration, and best practices for GenAI workloads.

## Implementation Checklist

Execute steps in order. Pick ONE decorator and configure it correctly.

> **Version note**: Examples use **Airflow 3.x** patterns (`airflow.sdk` imports). For **Airflow 2.x**, see Appendix A for import changes.
>
> **Cross-reference**: For human-in-the-loop operators (approval, human input), see the **airflow-hitl** skill. For advanced patterns (RAG, multi-agent, batch inference), see [reference/genai-patterns.md](reference/genai-patterns.md).

---

## Step 1: Install AI SDK + provider extra

**Why**: Ensure required packages and credentials exist at runtime.

Add to `requirements.txt`:

```
airflow-ai-sdk[<provider>]==<version>
```

| Provider | Extra | Example |
|----------|-------|---------|
| OpenAI | `openai` | `airflow-ai-sdk[openai]` |
| Anthropic | `anthropic` | `airflow-ai-sdk[anthropic]` |
| Google Vertex AI | `vertexai` | `airflow-ai-sdk[vertexai]` |
| Cohere | `cohere` | `airflow-ai-sdk[cohere]` |
| Groq | `groq` | `airflow-ai-sdk[groq]` |
| Mistral | `mistral` | `airflow-ai-sdk[mistral]` |
| AWS Bedrock | `bedrock` | `airflow-ai-sdk[bedrock]` |

**Additional dependency for `@task.embed`:**
```
sentence-transformers
```

### Configure API credentials

Set environment variable:

> **CRITICAL**: Do NOT hardcode secrets in code or DAG files.

```bash
# OpenAI
OPENAI_API_KEY="your-api-key"

# Anthropic
ANTHROPIC_API_KEY="your-api-key"

# Google (service account)
GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# AWS Bedrock (use IAM role or env vars)
AWS_ACCESS_KEY_ID="your-key"
AWS_SECRET_ACCESS_KEY="your-secret"
AWS_DEFAULT_REGION="us-east-1"
```

> **Astro Users**: Add environment variables via Astro UI under Deployment → Environment Variables.
>
> **Local dev note (Astro CLI projects)**: Put API keys in a local `.env` file that is ignored by git.

**Validate**:
- [ ] `airflow-ai-sdk[<provider>]` is added to dependencies
- [ ] Provider API credential is configured via environment variables (not hardcoded)
- [ ] If using `@task.embed`, `sentence-transformers` is added to dependencies

---

## Step 2: Choose decorator type

**Why**: Picking the right decorator up front avoids rewrites and mismatched outputs/XCom behavior.

Pick ONE based on use case:

| Decorator | Use case | Output | XCom Key |
|-----------|----------|--------|----------|
| `@task.llm` | Simple LLM call (text generation, analysis, summarization) | String or Pydantic model | `return_value` |
| `@task.llm_branch` | Route to different tasks based on LLM classification | Task ID(s) to execute | `return_value` |
| `@task.agent` | AI agent with tools (web search, API calls, custom functions) | String | `return_value` |
| `@task.embed` | Generate vector embeddings for RAG/similarity | `list[float]` per task run | `return_value` |

> **XCom Note**: All AI SDK decorators push their output to XCom using the key `return_value`. Access in downstream tasks via `ti.xcom_pull(task_ids='task_name')` or by passing the task result directly.

**Validate**:
- [ ] Exactly ONE decorator is selected for Step 3

---

## Step 3: Implement chosen decorator

### Option A: `@task.llm` (LLM call)

**Required parameters**:
- `model`: Model name (e.g., `"gpt-4o-mini"`, `"claude-3-sonnet"`)
- `system_prompt`: Instructions for the LLM (static across runs)

**Optional parameters**:
- `output_type`: Pydantic model class for structured output

> **CRITICAL**: The decorated function MUST return a `str` which becomes the user prompt.

```python
from airflow.sdk import dag, task, Param
from pendulum import datetime

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={
        "topic": Param(type="string", default="AI in healthcare"),
    },
)
def llm_example():

    @task.llm(
        model="gpt-4o-mini",
        system_prompt="You are a helpful assistant. Provide concise answers.",
        # output_type=MyPydanticModel,  # OPTIONAL: for structured output
    )
    def generate_summary(**context) -> str:
        topic = context["params"]["topic"]
        return f"Summarize the latest trends in {topic}."

    @task
    def process_result(llm_output: str):
        print(f"LLM Response: {llm_output}")
        return {"summary": llm_output, "length": len(llm_output)}

    result = generate_summary()
    process_result(result)

llm_example()
```

#### Structured output with Pydantic

```python
import airflow_ai_sdk as ai_sdk
from typing import Literal

class TicketAnalysis(ai_sdk.BaseModel):
    category: Literal["billing", "technical", "account", "general"]
    urgency: Literal["low", "medium", "high", "critical"]
    sentiment: Literal["positive", "neutral", "negative"]
    key_issues: list[str]

@task.llm(
    model="gpt-4o-mini",
    system_prompt="Analyze support tickets and extract structured information.",
    output_type=TicketAnalysis,
)
def analyze_ticket(ticket_text: str) -> str:
    return f"Analyze this ticket: {ticket_text}"
```

### Option B: `@task.llm_branch` (LLM-based routing)

> **CRITICAL**: Downstream task IDs MUST start with `handle_`.

**Required parameters**:
- `model`: Model name
- `system_prompt`: Instructions for classification

**Optional parameters**:
- `allow_multiple_branches`: If `True`, LLM can select multiple downstream tasks (default: `False`)

```python
from airflow.sdk import dag, task, chain, Param
from pendulum import datetime

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={
        "statement": Param(type="string", default="The sky is blue."),
    },
)
def llm_branch_example():

    @task
    def get_statement(**context) -> str:
        return context["params"]["statement"]

    @task.llm_branch(
        model="gpt-4o-mini",
        system_prompt="Classify the statement as true, false, or unclear.",
        allow_multiple_branches=False,
    )
    def classify_statement(statement: str) -> str:
        return statement

    @task
    def handle_true_statement():
        print("Statement classified as TRUE")

    @task
    def handle_false_statement():
        print("Statement classified as FALSE")

    @task
    def handle_unclear_statement():
        print("Statement classified as UNCLEAR")

    statement = get_statement()
    classification = classify_statement(statement=statement)

    chain(
        classification,
        [
            handle_true_statement(),
            handle_false_statement(),
            handle_unclear_statement(),
        ],
    )

llm_branch_example()
```

### Option C: `@task.agent` (AI agent with tools)

**Required parameters**:
- `agent`: A `pydantic_ai.Agent` instance

> **Note**: Any Python function can be provided as a tool. You can also use built-in tools like `duckduckgo_search_tool`.

```python
from airflow.sdk import dag, task, Param
from pydantic_ai import Agent
from pydantic_ai.common_tools.duckduckgo import duckduckgo_search_tool
from pendulum import datetime

# Define custom tool functions
def get_current_weather(latitude: float, longitude: float) -> str:
    import requests
    url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m"
    response = requests.get(url)
    return response.json()

# Create agent with tools (custom + built-in)
weather_agent = Agent(
    "gpt-4o-mini",
    system_prompt="""
    You create personalized weather reports based on user location.
    Use the get_current_weather tool to fetch weather data.
    """,
    tools=[get_current_weather, duckduckgo_search_tool],
)

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={
        "location": Param(type="string", default="New York"),
    },
)
def agent_example():

    @task.agent(agent=weather_agent)
    def create_weather_report(**context) -> str:
        location = context["params"]["location"]
        return f"Create a weather report for {location}."

    @task
    def process_report(report: str):
        print(f"Weather Report: {report}")
        return {"report": report, "word_count": len(report.split())}

    report = create_weather_report()
    process_report(report)

agent_example()
```

### Option D: `@task.embed` (embeddings)

**Optional parameters**:
- `model_name`: SentenceTransformer model (default: `"all-MiniLM-L12-v2"`)

> **CRITICAL**: Add `sentence-transformers` to `requirements.txt` (see Step 1).
>
> **CRITICAL**: The decorated function MUST return a `str` which will be passed to the embedding model.

```python
from airflow.sdk import dag, task
from pendulum import datetime

@dag(start_date=datetime(2025, 1, 1), schedule="@daily")
def embed_example():

    @task
    def get_texts() -> list[str]:
        return ["Hello world", "AI is amazing", "Data engineering"]

    @task.embed(model_name="BAAI/bge-small-en-v1.5")
    def embed_text(text: str) -> str:
        return text

    @task
    def store_embeddings(embeddings: list[list[float]]):
        print(f"Generated {len(embeddings)} embeddings")
        print(f"Embedding dimension: {len(embeddings[0])}")

    texts = get_texts()
    embeddings = embed_text.expand(text=texts)
    store_embeddings(embeddings)

embed_example()
```

**Validate**:
- [ ] Selected option uses imports consistent with your Airflow major version (see Appendix A for 2.x)
- [ ] The decorated function's required return type matches the decorator contract (`str` prompt)

---

## Step 4: Safety checks

> **Best practices**: For retries, XCom backends, pools, and rate limiting configuration, see [reference/genai-patterns.md](reference/genai-patterns.md#best-practices).

Before finalizing, verify:

- [ ] **API key configured**: Environment variable set, NOT hardcoded
- [ ] **Model name valid**: Matches provider's available models
- [ ] **Retries configured**: For API resilience (task-level or global)
- [ ] **Output type matches**: If using `output_type`, Pydantic model is defined
- [ ] **Branch task IDs**: For `@task.llm_branch`, downstream IDs start with `handle_`
- [ ] **Agent tools**: For `@task.agent`, all tools are defined and imported
- [ ] **No top-level LLM calls**: DAG files parsed every 30s; LLM calls must be inside tasks
- [ ] **XCom size considered**: Object storage backend or write results to storage directly

**User must test**:
- [ ] Trigger a DAG parse (scheduler/webserver) and confirm no network calls occur at import/parse time
- [ ] Run the DAG once and confirm the AI task succeeds and downstream tasks receive expected XCom output

---

## Advanced Patterns

For advanced GenAI orchestration patterns, see [reference/genai-patterns.md](reference/genai-patterns.md):

- **RAG pipelines**: Embeddings + vector DB + LLM generation
- **Prompt-chaining**: Sequential LLM refinement
- **Routing**: LLM-based branching with `@task.llm_branch`
- **Multi-agent**: Orchestrator-worker-synthesizer patterns
- **Batch inference**: Dynamic task mapping with `.expand()`
- **Event-driven inference**: Kafka/SQS triggers, API-driven DAG runs
- **Fine-tuning**: Custom deferrable operators

---

## Appendix A: Airflow 2.x Compatibility

| Airflow 3.x | Airflow 2.x |
|-------------|-------------|
| `from airflow.sdk import dag, task` | `from airflow.decorators import dag, task` |
| `from airflow.sdk import chain` | `from airflow.models.baseoperator import chain` |

---

## Reference

- Airflow AI SDK docs: https://github.com/astronomer/airflow-ai-sdk
- Pydantic AI (for agents): https://ai.pydantic.dev/
- SentenceTransformers (for embeddings): https://www.sbert.net/

---

## Related Skills

- **airflow-hitl**: For human-in-the-loop approval and input operators
- **authoring-dags**: For general DAG writing best practices
- **testing-dags**: For testing DAGs with debugging cycles
