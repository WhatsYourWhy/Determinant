# Determinant Project Notes

This document captures the agreed project skeleton, implementation phases, core module designs, and testing/validation plan.

---

## 1. Project Skeleton (Top-Level Layout)

**Goal:** Every new idea has a place. No mystery folders.

```text
determinant/
├── determinant/
│   ├── __init__.py
│   ├── state.py
│   ├── step.py
│   ├── graph.py
│   ├── run.py
│   ├── ledger.py
│   ├── validator.py
│   ├── errors.py
│   ├── hashing.py
│   └── json_canonical.py
├── examples/
│   ├── document_pipeline/
│   │   ├── graph.json
│   │   ├── config.json
│   │   ├── input_state.json
│   │   └── run_example.py
│   └── math_only_agent/
├── tests/
│   ├── test_state.py
│   ├── test_step.py
│   ├── test_graph.py
│   ├── test_run_determinism.py
│   ├── test_ledger_schema.py
│   └── test_validator.py
├── docs/
│   ├── DESIGN.md        # already drafted
│   ├── LEDGER_SCHEMA.md # from our last message
│   └── ROADMAP.md
├── README.md
├── pyproject.toml
└── LICENSE
```

**Rule:**
If something doesn’t clearly fit in that skeleton, it’s probably feature creep.

---

## 2. Implementation Phases (with DONE Criteria)

### Phase 0 — “Bare Spine”

**Objective:** A run that does *almost nothing* but obeys determinism & ledger rules.

**Scope:**

* `State` with:

  * `from_file()`, `to_file()`
  * `hash()` (SHA-256 of canonical JSON)
* `Step` base class:

  * `.execute(state: State) -> (State, events, artifacts)`
* `Graph` with:

  * simple ordered list of steps
* `run()` with:

  * sequential execution over steps
  * writing `runs/<run_id>/ledger.ndjson`
  * writing state snapshots
* Minimal ledger implementation:

  * `RUN_START`, `STEP_START`, `STEP_END`, `RUN_END` only

**DONE when:**

* You can run `python examples/document_pipeline/run_example.py`
* Two runs with same inputs → bit-identical:

  * final state file
  * ledger file
* `test_run_determinism.py` passes.

---

### Phase 1 — “Full Ledger”

**Objective:** The ledger matches the spec we defined (events, artifacts, hash chain).

**Scope:**

* Implement `ARTIFACT_WRITTEN` records
* Implement `STEP_EVENT` records
* Implement hash chain (`prev_hash`, `hash`)
* Add `manifest.json` generation
* Add `meta/graph.json`, `meta/config.json`, `meta/env.json` stubs

**DONE when:**

* `validator.py` can:

  * confirm hash chain is intact
  * confirm state/artifact hashes match content
  * confirm record ordering is valid
* `test_ledger_schema.py` + `test_validator.py` pass.

---

### Phase 2 — “Branching & Error Handling”

**Objective:** Realistic control flow without breaking determinism.

**Scope:**

* Extend `Graph` to support:

  * conditional branching on state (simple rule language)
* Add `RUN_FAIL` records
* Support per-step `status` (OK / FAILED / SKIPPED)
* Rudimentary rule engine for branch conditions (deterministic only)

**DONE when:**

* Example graph with conditional branch runs correctly.
* When a step fails:

  * `RUN_FAIL` is emitted
  * replay stops at same point, same error
* `test_graph.py` covers:

  * straight-line execution
  * branching
  * failure handling

---

### Phase 3 — “Public API & Examples”

**Objective:** Make this usable by someone who isn’t you.

**Scope:**

* Clean public API surface:

  * `determinant.State`
  * `determinant.Step`
  * `determinant.Graph`
  * `determinant.run`
* Two examples:

  1. **Document pipeline** (parse/score markdown)
  2. **Math-only pipeline** (e.g., anomaly scoring on numeric data)
* Basic CLI:

  * `determinant run meta/graph.json state/initial.json`

**DONE when:**

* A new user can:

  * read README
  * run an example
  * understand ledger structure from docs
* `ROADMAP.md` exists and matches reality.

---

## 3. Core Module Design Outlines

### 3.1 `state.py`

**Responsibilities:**

* Represent structured state
* Provide serialization and hashing

**Outline:**

```python
@dataclass(frozen=True)
class State:
    data: dict[str, Any]

    @classmethod
    def from_file(cls, path: str) -> "State": ...
    def to_file(self, path: str) -> None: ...
    def to_canonical_json_bytes(self) -> bytes: ...
    def sha256(self) -> str: ...
```

Constraints:

* `data` must be JSON-serializable.
* No time, no random, no IO hidden inside.

---

### 3.2 `step.py`

**Responsibilities:**

* Define the contract for deterministic steps
* Provide event + artifact wrappers

**Outline:**

```python
@dataclass
class StepResult:
    state: State
    events: list["StepEvent"]
    artifacts: list["Artifact"]

class Step(ABC):
    step_id: str  # default to class name

    @abstractmethod
    def execute(self, state: State) -> StepResult:
        ...
```

Events:

```python
@dataclass
class StepEvent:
    event_type: str  # "INFO" | "WARN" | "ERROR"
    code: str        # machine-readable event code
    message: str
    data: dict[str, Any]
```

Artifacts:

```python
@dataclass
class Artifact:
    artifact_id: str
    logical_name: str
    media_type: str
    path: str  # relative path under runs/<run_id>/artifacts
    bytes: bytes
```

---

### 3.3 `graph.py`

**Responsibilities:**

* Represent the execution graph
* Provide ordering and branching

**v0 (no branching yet):**

```python
@dataclass
class Graph:
    graph_id: str
    version: str
    steps: list[Step]
```

Later:

* Add `nodes`, `edges`, and condition rules matching `graph.json`.

---

### 3.4 `run.py`

**Responsibilities:**

* Orchestrate a run
* Talk to `ledger.py` and file system

**Outline:**

```python
@dataclass
class RunConfig:
    run_id: str | None
    seed: int
    output_dir: str

@dataclass
class RunResult:
    run_id: str
    final_state: State | None
    status: str  # "OK" | "FAILED"
    ledger_path: str

def run(graph: Graph, initial_state: State, config: RunConfig) -> RunResult:
    # 1. prepare run dir
    # 2. write meta/graph.json, meta/config.json, meta/env.json
    # 3. init ledger (RUN_START)
    # 4. iterate over steps:
    #    - write STEP_START
    #    - call step.execute
    #    - write STEP_EVENT, ARTIFACT_WRITTEN, STEP_END
    # 5. write RUN_END or RUN_FAIL
    ...
```

---

### 3.5 `ledger.py`

**Responsibilities:**

* Build ledger records
* Maintain hash chain
* Canonical JSON encoding
* Write NDJSON file

**Outline:**

```python
class LedgerWriter:
    def __init__(self, path: str, run_id: str): ...
    def write_run_start(...): ...
    def write_step_start(...): ...
    def write_step_event(...): ...
    def write_artifact_written(...): ...
    def write_step_end(...): ...
    def write_run_end(...): ...
    def write_run_fail(...): ...
```

Internals:

* Track `seq`
* Track `prev_hash`
* Canonicalize JSON, compute `hash`, then write line.

---

### 3.6 `validator.py`

**Responsibilities:**

* Validate ledger correctness
* Recompute hashes
* Cross-check state/artifact files

**Outline:**

```python
@dataclass
class ValidationIssue:
    level: str  # "ERROR" | "WARN"
    code: str
    message: str

@dataclass
class ValidationResult:
    ok: bool
    issues: list[ValidationIssue]

def validate_run(run_dir: str) -> ValidationResult:
    # 1. load ledger.ndjson
    # 2. verify hash chain
    # 3. verify required record types presence & order
    # 4. verify referenced file hashes match
    ...
```

---

## 4. Testing & Validation Plan

### 4.1 Determinism Tests

* `test_run_determinism.py`

  * Arrange:

    * same graph, config, initial state, seed
  * Act:

    * run twice, with fresh run_ids
  * Assert:

    * final state hash equal
    * ledger.ndjson bytes equal (once you normalize run_id if needed)
* Also one **negative** test:

  * change config threshold by 1 → state hashes diverge at expected step index

### 4.2 Ledger Schema Tests

* `test_ledger_schema.py`

  * Validate that records conform to required fields per type
  * Validate `schema` field is present and correct
  * Validate `type` is one of allowed enums
  * Validate `seq` increments monotonically

### 4.3 Validator Tests

* `test_validator.py`

  * Happy path:

    * valid run → `ok == True`, issues empty
  * Broken hash chain:

    * manually edit one record → validator flags `HASH_CHAIN_BROKEN`
  * Missing state file:

    * delete one state file → validator flags `MISSING_STATE_FILE`

### 4.4 Graph & Branching Tests (Phase 2)

* `test_graph.py`

  * Straight-line graph runs expected steps in order.
  * Branching graph runs only the taken branch.
  * Failed step:

    * `RUN_FAIL` emitted
    * no further step records.
