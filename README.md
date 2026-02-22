# Determinant

**A deterministic runtime for building auditable, replayable agent systems.**

Determinant is not an “AI agent framework.”
It is a **runtime for executing structured programs** that may include agents, where **every run is reproducible, inspectable, and explainable**.

If you want autonomy, creativity, or emergent behavior, this is not the tool you’re looking for.

---

## Why Determinant Exists

Most agent frameworks optimize for:

* Emergence
* Autonomy
* Conversational flexibility
* Demo appeal

They fail at:

* Reproducibility
* Auditability
* Debuggability
* Safety
* Trust

Determinant exists for teams who have already learned the hard lesson:

> *If you can’t replay it, you can’t trust it.*

---

## What Determinant Is

Determinant is a **deterministic execution runtime** built around four ideas:

1. **Explicit State**
   All state is structured, serializable, and visible.
   No hidden memory. No implicit context.

2. **Deterministic Steps**
   Each step is a pure, inspectable transformation of state.
   Given the same inputs, it produces the same outputs.

3. **Explicit Control Flow**
   Execution order and branching are defined by rules — not by LLM decisions.

4. **Replayable Runs**
   Every execution produces a ledger that can be replayed, diffed, and audited.

If the inputs, code, configuration, and seed are identical, **the execution is identical**.

---

## What Determinant Is Not

Determinant explicitly does **not** support:

* Agents that decide what to do next
* Hidden or implicit memory
* “Let the LLM figure it out” control flow
* Autonomous goal pursuit
* Cloud-only execution
* Undebuggable chains of thought
* Live web access by default
* Vibes

These are non-goals, not missing features.

---

## Design Philosophy

Determinant treats intelligence as something you **compile**, not something you improvise at runtime.

LLMs (if used at all) belong in **design-time workflows**:

* generating rules
* proposing transformations
* drafting schemas
* suggesting heuristics

At runtime, Determinant executes **fixed structure**.

Think:

* Makefiles, not copilots
* SQL, not chat
* Terraform, not “AI decides infra”

---

## Core Concepts

### State

An immutable, structured snapshot of the system at a point in time.

* Fully serializable
* Versionable
* Diffable

### Step

A deterministic operation:

```
(state) → (new_state, events, artifacts)
```

No side effects outside the state and declared artifacts.

### Graph

An explicit execution graph:

* Ordered steps
* Conditional branches defined by rules
* No dynamic agent routing

### Run

A single execution of a graph:

* Produces a complete execution ledger
* Can be replayed semantically (state/artifact hashes and step records)
* Can be diffed against other runs

---

## Guarantees

Determinant makes the following guarantees:

* **Replayability**
  Same graph/state/config/seed produces the same state and artifact hashes.

* **Auditability**
  Every step transition, event, and artifact write is logged in `ledger.ndjson`.

* **Explainability**
  Divergence between runs can be located by comparing manifest and ledger hashes.

* **Local-first**
  The runtime executes local Python code only; any network behavior must come from user steps.

If you break these guarantees, you are using Determinant incorrectly.

---

## Example (Minimal)

```python
from determinant import State, Step, StepEvent, StepResult, Graph, RunConfig, run

class AddValue(Step):
    def execute(self, state: State, config: dict[str, object], seed: int) -> StepResult:
        _ = seed
        inc = int(config.get("increment", 1))
        value = int(state.data.get("value", 0)) + inc
        return StepResult(
            state=State({"value": value}),
            events=[StepEvent(event_type="INFO", code="VALUE_UPDATED", message="value updated")],
        )


graph = Graph(
    graph_id="minimal",
    version="v1",
    steps=[AddValue()],
)

config_data = {
    "seed": 42,
    "output_dir": "output",
}
run_config = RunConfig(
    run_id="example",
    seed=42,
    output_dir="output",
    config_data=config_data,
)
result = run(
    graph=graph,
    initial_state=State({"value": 0}),
    config=run_config,
)

print(result.status)      # COMPLETED
print(result.ledger_path) # output/runs/example/ledger.ndjson
```

Running this twice with the same inputs will produce the same final state and artifact hashes.
Ledger files include timestamps, so compare semantic fields rather than full file bytes.

---

## Who This Is For

Determinant is built for:

* Infrastructure and platform teams
* Security- and compliance-sensitive environments
* ML engineers who need control, not autonomy
* Organizations that must explain system behavior under audit
* Anyone who has already been burned by agent chaos

If you are optimizing for speed-to-demo, this will feel slow.
If you are optimizing for trust, this will feel obvious.

---

## Status

Determinant is **early and intentionally narrow**.

The current focus:

* Locking execution semantics
* Enforcing determinism
* Building rock-solid replay and diff guarantees

Features will be added **only if they do not weaken these constraints**.

---

## Testing

Install the package in editable mode so tests can import `determinant` directly:

```bash
python -m pip install -e .
python -m pytest -q
```

If you prefer not to install in editable mode, set `PYTHONPATH` to the repo root:

```bash
PYTHONPATH=. python -m pytest -q
```

---

## Non-Negotiables

* No hidden state
* No implicit memory
* No LLM-controlled execution
* No magic
* No exceptions

---

## License

Open source.
Exact license to be finalized.

---

## Final Note

Determinant is not trying to win the agent hype cycle.

It is trying to make **agent systems survivable**.

If that resonates, welcome.
If not, there are plenty of other tools.
