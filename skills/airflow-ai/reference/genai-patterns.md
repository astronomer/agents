# Advanced GenAI Patterns in Airflow

This reference covers advanced orchestration patterns for GenAI workloads. For basic AI SDK usage, see the main [SKILL.md](../SKILL.md).

> **Prerequisites**: Verify your Airflow version supports `airflow.sdk` and AI task decorators before implementing these patterns.

## Table of Contents

- [Pattern Selection Guide](#pattern-selection-guide)
- [Scheduling Patterns for GenAI](#scheduling-patterns-for-genai)
- [Dynamic Task Mapping](#dynamic-task-mapping)
- [Pattern A: RAG Pipeline](#pattern-a-rag-pipeline)
- [Pattern B: Prompt-Chaining](#pattern-b-prompt-chaining)
- [Pattern C: Routing](#pattern-c-routing)
- [Pattern D: Multi-Agent](#pattern-d-multi-agent-orchestrator-worker-synthesizer)
- [Pattern E: Batch Inference](#pattern-e-batch-inference)
- [Pattern F: Fine-Tuning](#pattern-f-fine-tuning-custom-operator)
- [Best Practices](#best-practices)

---

## Pattern Selection Guide

| Pattern | Use case | Key components |
|---------|----------|----------------|
| RAG | Query with context from vector DB | `@task.embed` + vector DB + `@task.llm` |
| Prompt-chaining | Sequential LLM refinement | Multiple `@task.llm` in sequence |
| Routing | LLM-based branching | `@task.llm_branch` |
| Multi-agent | Specialized agents collaborate | Multiple `@task.agent` |
| Batch inference | Process data in bulk | `@task.llm` + `.expand()` |
| Ad-hoc inference | Request-driven inference | API triggers or `AssetWatcher` |
| Fine-tuning | Train custom model | Custom deferrable operator |

---

## Scheduling Patterns for GenAI

### Data-Aware Scheduling with Assets

Schedule DAGs based on upstream data updates:

```python
from airflow.sdk import dag, task, Asset
from pendulum import datetime

# Producer DAG
@dag(start_date=datetime(2025, 1, 1), schedule="@daily")
def producer():
    @task(outlets=[Asset("embeddings_updated")])
    def generate_embeddings():
        # ... create embeddings
        pass
    generate_embeddings()

producer()

# Consumer DAG - runs when Asset is updated
@dag(start_date=datetime(2025, 1, 1), schedule=[Asset("embeddings_updated")])
def consumer():
    @task
    def use_embeddings():
        pass
    use_embeddings()

consumer()
```

**Conditional scheduling** (AND/OR):

```python
@dag(
    schedule=(
        Asset("data_ready") | Asset("manual_trigger")  # OR
    ),
)
def my_dag(): ...

@dag(
    schedule=(
        Asset("data_a") & Asset("data_b")  # AND - both required
    ),
)
def my_dag(): ...
```

### Combined Asset + Time Scheduling

Run DAG either when Assets update OR on a time schedule:

```python
from airflow.sdk import Asset, dag
from airflow.timetables.Assets import AssetOrTimeSchedule
from airflow.timetables.trigger import CronTriggerTimetable
from pendulum import datetime

@dag(
    start_date=datetime(2025, 1, 1),
    schedule=AssetOrTimeSchedule(
        timetable=CronTriggerTimetable("0 0 * * *", timezone="UTC"),
        Assets=(Asset("data_ready") | Asset("backup_trigger")),
    ),
)
def combined_schedule_dag():
    ...

combined_schedule_dag()
```

### Event-Driven Scheduling (Kafka/SQS)

For ad-hoc inference triggered by external events:

> **Requirements**: `apache-airflow-providers-apache-kafka>=1.9.0` and `apache-airflow-providers-common-messaging>=1.0.2`.
>
> **Mental model**:
> - A **Trigger** polls the message queue; when it finds a new message it emits a `TriggerEvent` and the message is deleted.
> - An **AssetWatcher** listens for trigger events and updates an **Asset**, creating an **AssetEvent**.
> - The trigger payload is attached to the `AssetEvent` in its `extra` dictionary.

```python
import json
from airflow.providers.common.messaging.triggers.msg_queue import MessageQueueTrigger
from airflow.sdk import dag, task, Asset, AssetWatcher
from pendulum import datetime

# Define message handler
def parse_message(*args, **kwargs):
    message = args[-1]
    return json.loads(message.value())

# Create trigger watching Kafka topic
trigger = MessageQueueTrigger(
    queue="kafka://localhost:9092/inference_requests",
    apply_function="dags.event_driven_dag.parse_message",
)

# Asset with watcher
inference_asset = Asset(
    "inference_request",
    watchers=[AssetWatcher(name="kafka_watcher", trigger=trigger)],
)

@dag(start_date=datetime(2025, 1, 1), schedule=[inference_asset])
def event_driven_inference():

    @task
    def get_request(**context):
        events = context["triggering_asset_events"]
        for event in events[inference_asset]:
            return event.extra["payload"]

    @task.llm(model="gpt-4o-mini", system_prompt="Process the request.")
    def process(request: dict):
        return str(request)

    req = get_request()
    process(req)

event_driven_inference()
```

### Trigger via Airflow REST API (push pattern)

For request-driven ad-hoc inference, send a POST request to the Airflow REST API to trigger a DAG run:

```bash
curl -X POST "https://airflow.example.com/api/v2/dags/my_inference_dag/dagRuns" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"conf": {"input": "process this text"}}'
```

---

## Dynamic Task Mapping

Process variable amounts of data in parallel. The number of mapped tasks adjusts at runtime.

### Basic `.expand()` (single parameter)

```python
@task.llm(model="gpt-4o-mini", system_prompt="Summarize.")
def summarize(text: str) -> str:
    return text

# Creates N parallel tasks, one per item
results = summarize.expand(text=["doc1", "doc2", "doc3"])
```

### `.partial()` + `.expand()` (mixed parameters)

```python
from airflow.sdk import dag, task, get_current_context

@task(map_index_template="{{ my_custom_map_index }}")
def process(x: int, y: int, model: str):
    context = get_current_context()
    context["my_custom_map_index"] = f"Processing x={x}"
    return x + y

# y and model stay constant, x varies
results = process.partial(y=10, model="gpt-4o").expand(x=[1, 2, 3])
```

### `.expand_kwargs()` (multiple varying parameters)

```python
@task
def zip_inputs(texts, analyses):
    return [{"text": t, "analysis": a} for t, a in zip(texts, analyses)]

@task.llm(model="gpt-4o-mini", system_prompt="Generate response.")
def generate_response(text: str, analysis: dict) -> str:
    return f"Text: {text}\nAnalysis: {analysis}"

# Expand with multiple parameters per task instance
pairs = zip_inputs(texts, analyses)
responses = generate_response.expand_kwargs(pairs)
```

---

## Pattern A: RAG Pipeline

```python
from airflow.sdk import dag, task, chain, Param
from pendulum import datetime

COLLECTION = "my_collection"
WEAVIATE_CONN = "weaviate_default"

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={"query": Param("What is AI?", type="string")},
)
def rag_pipeline():

    @task
    def get_documents():
        return ["Document 1 content", "Document 2 content", "Document 3 content"]

    @task.embed(model_name="BAAI/bge-small-en-v1.5")
    def embed_doc(text: str):
        return text

    @task
    def load_to_vector_db(texts: list, embeds: list):
        from airflow.providers.weaviate.hooks.weaviate import WeaviateHook
        from weaviate.classes.data import DataObject
        hook = WeaviateHook(WEAVIATE_CONN)
        client = hook.get_conn()
        collection = client.collections.get(COLLECTION)
        for text, emb in zip(texts, embeds):
            collection.data.insert_many([DataObject(properties={"text": text}, vector=emb)])

    @task.embed(model_name="BAAI/bge-small-en-v1.5")
    def embed_query(**context):
        return context["params"]["query"]

    @task
    def retrieve(query_embed: list):
        from airflow.providers.weaviate.hooks.weaviate import WeaviateHook
        hook = WeaviateHook(WEAVIATE_CONN)
        client = hook.get_conn()
        results = client.collections.get(COLLECTION).query.near_vector(near_vector=query_embed, limit=3)
        return [r.properties["text"] for r in results.objects]

    @task.llm(model="gpt-4o-mini", system_prompt="Answer using only the provided context.")
    def generate_answer(context_docs: list, **context):
        query = context["params"]["query"]
        ctx = "\n".join(context_docs)
        return f"Context:\n{ctx}\n\nQuestion: {query}"

    docs = get_documents()
    embeds = embed_doc.expand(text=docs)
    load_task = load_to_vector_db(docs, embeds)
    q_embed = embed_query()
    retrieved = retrieve(q_embed)
    chain(load_task, retrieved)
    generate_answer(retrieved)

rag_pipeline()
```

---

## Pattern B: Prompt-Chaining

```python
from airflow.sdk import dag, task, Param
from typing import Literal
import airflow_ai_sdk as ai_sdk
from pendulum import datetime

class TicketAnalysis(ai_sdk.BaseModel):
    category: Literal["billing", "technical", "account"]
    urgency: Literal["low", "medium", "high"]
    key_issues: list[str]

class CustomerResponse(ai_sdk.BaseModel):
    message: str
    next_steps: list[str]

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={"ticket": Param("I can't login to my account", type="string")},
)
def prompt_chaining():

    @task.llm(
        model="gpt-4o-mini",
        system_prompt="Analyze support tickets.",
        output_type=TicketAnalysis,
    )
    def analyze_ticket(**context):
        return f"Analyze: {context['params']['ticket']}"

    @task.llm(
        model="gpt-4o-mini",
        system_prompt="Generate customer response based on analysis.",
        output_type=CustomerResponse,
    )
    def generate_response(analysis: TicketAnalysis, **context):
        return f"Ticket: {context['params']['ticket']}\nAnalysis: {analysis}"

    @task
    def send_response(response: CustomerResponse):
        print(f"Sending: {response['message']}")

    analysis = analyze_ticket()
    response = generate_response(analysis)
    send_response(response)

prompt_chaining()
```

---

## Pattern C: Routing

```python
from airflow.sdk import dag, task, chain, Param
from pendulum import datetime

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={"incident": Param("Server is down", type="string")},
)
def routing_pattern():

    @task.llm_branch(
        model="gpt-4o-mini",
        system_prompt="""Classify incident severity:
        - handle_critical: life-threatening, system down
        - handle_standard: needs attention, not urgent
        - handle_low: minor issues""",
    )
    def route_incident(**context):
        return context["params"]["incident"]

    @task
    def handle_critical():
        print("CRITICAL: Immediate response")

    @task
    def handle_standard():
        print("STANDARD: Queue for next shift")

    @task
    def handle_low():
        print("LOW: Add to backlog")

    route = route_incident()
    chain(route, [handle_critical(), handle_standard(), handle_low()])

routing_pattern()
```

---

## Pattern D: Multi-Agent (Orchestrator-Worker-Synthesizer)

This pattern uses an **orchestrator** to delegate tasks to **worker** agents, then a **synthesizer** to combine results.

```python
from airflow.sdk import dag, task, Param
from pydantic_ai import Agent
from pendulum import datetime

# Define specialized agents
def search_web(query: str) -> str:
    return f"Search results for: {query}"

# Worker agents (specialized)
research_agent = Agent("gpt-4o-mini", system_prompt="Research analyst", tools=[search_web])
financial_agent = Agent("gpt-4o-mini", system_prompt="Financial analyst")
# Synthesizer agent
synthesis_agent = Agent("gpt-4o-mini", system_prompt="Synthesize analyses into report")

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={"company": Param("Acme Corp", type="string")},
)
def multi_agent():

    @task.agent(agent=research_agent)
    def market_research(**context):
        return f"Research market for {context['params']['company']}"

    @task.agent(agent=financial_agent)
    def financial_analysis(**context):
        return f"Analyze financials for {context['params']['company']}"

    @task.agent(agent=synthesis_agent)
    def synthesize(research: str, financial: str):
        return f"Combine:\n{research}\n{financial}"

    @task
    def output_report(report: str):
        print(report)

    r = market_research()
    f = financial_analysis()
    s = synthesize(r, f)
    output_report(s)

multi_agent()
```

---

## Pattern E: Batch Inference

```python
from airflow.sdk import dag, task, Param
from typing import Literal
import airflow_ai_sdk as ai_sdk
from pendulum import datetime

class Sentiment(ai_sdk.BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    summary: str

@dag(
    start_date=datetime(2025, 1, 1),
    schedule="@daily",
    params={"reviews": Param(["Great product!", "Terrible service", "It's okay"], type="array")},
)
def batch_inference():

    @task
    def get_reviews(**context):
        return context["params"]["reviews"]

    @task.llm(model="gpt-4o-mini", system_prompt="Analyze sentiment.", output_type=Sentiment)
    def analyze(review: str):
        return review

    @task
    def aggregate(results: list):
        pos = sum(1 for r in results if r["sentiment"] == "positive")
        print(f"Positive: {pos}/{len(results)}")

    reviews = get_reviews()
    analyzed = analyze.expand(review=reviews)
    aggregate(analyzed)

batch_inference()
```

---

## Pattern F: Fine-Tuning (Custom Operator)

Use a custom deferrable fine-tuning operator that waits asynchronously for the job to complete.

```python
from airflow.sdk import dag, task
from include.custom_operators.gpt_fine_tune import OpenAIFineTuneOperator
from pendulum import datetime

@dag(start_date=datetime(2025, 1, 1), schedule=None)
def fine_tuning():
    _EXAMPLES_FILE_PATH = "include/examples/train/training_data.jsonl"
    _VALIDATION_FILE_PATH = "include/examples/validation/validation_data.jsonl"

    @task
    def upload_training_data():
        from openai import OpenAI
        client = OpenAI()
        f = client.files.create(file=open(_EXAMPLES_FILE_PATH, "rb"), purpose="fine-tune")
        return f.id

    @task
    def upload_validation_data():
        from openai import OpenAI
        client = OpenAI()
        f = client.files.create(file=open(_VALIDATION_FILE_PATH, "rb"), purpose="fine-tune")
        return f.id

    training_file_id = upload_training_data()
    validation_file_id = upload_validation_data()

    fine_tune = OpenAIFineTuneOperator(
        task_id="fine_tune",
        fine_tuning_file_id=training_file_id,
        validation_file_id=validation_file_id,
        model="gpt-4o-mini-2024-07-18",
        suffix="{{ dag_run.run_id }}",
        wait_for_completion=True,
        deferrable=True,
        poke_interval=5,
        retries=0,
    )

    @task
    def log_model(model_id: str):
        print(f"Fine-tuned model: {model_id}")

    fine_tune >> log_model(fine_tune.output)

fine_tuning()
```

---

## Best Practices

1. **Retries**: Set `retries=3` on LLM tasks for API resilience
2. **XCom Backend**: Use object storage for large responses
3. **Idempotency**: LLM outputs vary; design downstream tasks accordingly
4. **Rate Limits**: Use pools to limit concurrent API calls
5. **Costs**: Monitor token usage; use smaller models for classification
6. **No top-level API calls**: DAG files are parsed every 30 seconds

```python
# ❌ BAD - runs on every DAG parse (every 30s!)
result = openai.chat.completions.create(...)

@dag
def my_dag():
    # ✅ GOOD - only runs when task executes
    @task.llm(model="gpt-4o-mini", system_prompt="...")
    def my_task():
        return "prompt"
```

7. **Use pools for rate limiting**:

```python
# In Airflow UI: Admin → Pools → Create "openai_api_pool" with slots=5

@task.llm(
    model="gpt-4o-mini",
    system_prompt="...",
    pool="openai_api_pool",
    pool_slots=1,
)
def rate_limited_llm_call():
    return "prompt"
```

---

## Reference

- Airflow AI SDK: https://github.com/astronomer/airflow-ai-sdk
- Pydantic AI: https://ai.pydantic.dev/
- SentenceTransformers: https://www.sbert.net/
- Weaviate Provider: https://airflow.apache.org/docs/apache-airflow-providers-weaviate/

---

## Related Skills

- **airflow-ai**: For basic AI SDK usage and decorator implementation
- **airflow-hitl**: For human-in-the-loop approval and input operators
- **authoring-dags**: For general DAG writing best practices
- **testing-dags**: For testing DAGs with debugging cycles
