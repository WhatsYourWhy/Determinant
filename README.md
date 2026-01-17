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
* Can be replayed byte-for-byte
* Can be diffed against other runs

---

## Guarantees

Determinant makes the following guarantees:

* **Replayability**
  Same inputs → same outputs

* **Auditability**
  Every step, transition, and artifact is logged

* **Explainability**
  Divergence between runs is attributable to explicit differences

* **Local-first**
  Runs fully offline by default

If you break these guarantees, you are using Determinant incorrectly.

---

## Example (Minimal)

```python
from determinant import State, Step, Graph, run

class ParseDocs(Step):
    def execute(self, state: State):
        ...

class ScoreDocs(Step):
    def execute(self, state: State):
        ...

graph = Graph(steps=[
    ParseDocs(),
    ScoreDocs(),
])

result = run(
    graph=graph,
    initial_state=State.from_file("input.json"),
    seed=42
)
```

Running this twice with the same inputs will produce **identical results and ledgers**.

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
