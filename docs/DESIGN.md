Determinant — Design Specification

This document defines the execution invariants and threat model for Determinant.

If an implementation violates this document, it is incorrect, even if it appears to work.

1. Core Design Goal

Determinant exists to make agent systems replayable, auditable, and explainable by construction.

This goal supersedes:

Convenience

Flexibility

Performance optimizations

Compatibility with other agent frameworks

Any feature that weakens determinism, auditability, or replayability is out of scope.

2. Execution Invariants (Non-Negotiable)

These invariants must hold for every run.

2.1 Determinism Invariant

Given:

Identical graph definition

Identical initial state

Identical configuration

Identical seed

Identical runtime version

The system must produce:

Identical final state

Identical artifacts (byte-for-byte)

Identical execution ledger

If this is not true, the runtime is broken.

2.2 Explicit State Invariant

All mutable information must be represented in the State object.

Forbidden:

Hidden globals

Implicit memory

Environment-based state (except explicitly injected)

Time-based access without controlled injection

State must be:

Fully serializable

Hashable

Versionable

Diffable

If something affects execution, it must appear in state.

2.3 Pure Step Invariant

Each Step must behave as a deterministic transformation:

(state, config, seed) → (new_state, events, artifacts)


Rules:

No side effects outside declared artifacts

No network access unless explicitly permitted and mocked

No reading system time

No uncontrolled randomness

Any randomness must be:

Seeded

Explicit

Recorded in the ledger

2.4 Explicit Control Flow Invariant

Execution order and branching must be defined outside of model inference.

Allowed:

Rule-based branching

State-based conditions

Static graphs

Forbidden:

“Let the agent decide what to do next”

LLM-selected execution paths

Dynamic graph mutation during a run

The execution graph is fixed at run start.

2.5 Ledger Completeness Invariant

Every run must produce a complete execution ledger capturing:

Graph version

Runtime version

Step order

State hashes before and after each step

Events emitted by each step

Artifact hashes

Seed and configuration

If an execution cannot be reconstructed from the ledger, the ledger is insufficient.

2.6 Deterministic Semantics vs Incidental Metadata

The ledger contains both semantic data (which defines the execution) and incidental metadata
(which may vary without changing meaning). Semantic equality between two runs is defined by
matching:

Graph, configuration, and environment hashes

Step identity and version

State hashes (including the final_state hash)

Artifact hashes or stable artifact IDs

Event codes and event data

Run status

The following fields are always ignored for semantic comparisons:

run_id

seq

ts_utc

hash

prev_hash

The following fields are conditionally ignored for semantic comparisons when they do not
affect program meaning:

message

Performance metrics such as duration_ms and size_bytes

Regardless of semantic comparisons, the hash chain must still cover full ledger records
(excluding the hash field itself) to provide integrity and tamper evidence for incidental
metadata as well.

3. Execution Model
3.1 State

Immutable snapshot

Replaced, not mutated

Identified by content hash

State transitions form a linear or branched history fully captured in the ledger.

3.2 Steps

Steps are not agents in the anthropomorphic sense.

They are deterministic operators.

A step:

Receives the current state

Emits:

a new state

zero or more events

zero or more artifacts

Steps may fail, but failure must be explicit and logged.

3.2.1 Step Identity and Versioning

Each Step must declare a stable logical name, step_id. This identifier is used to match
behavior across runs and must not change when code is relocated, refactored, or imported
from a different module path.

Each Step must also expose a step_version computed from the source file that defines the
Step subclass. The required format is:

step_version = "src:<sha256(module_file_bytes)>"

This ensures that any change to the defining file produces a new version.

All step-specific configuration that can affect behavior must be fully serialized and
hashed. The canonical configuration must be stored in config.json (or State if it is
runtime-derived), and the hash must be referenced from RUN_START.inputs.config.sha256.

Hidden or unserialized step parameters that influence outcomes are explicitly forbidden.

3.3 Graph

A Graph defines:

Step ordering

Branching rules

Termination conditions

Graphs are:

Static during execution

Serializable

Versioned

3.4 Run

A Run is a concrete execution instance.

A Run:

Has a unique ID

Produces a ledger

Can be replayed exactly

Replays must not depend on:

External services

Clock time

Network availability

4. Threat Model

Determinant assumes hostile failure modes, not friendly usage.

This section defines what the system must defend against.

4.1 Threat: Hidden Nondeterminism

Examples:

Reading system time

Unseeded random calls

Non-deterministic iteration order

Floating-point instability across platforms

Mitigations:

Runtime checks for time access

Seed enforcement

Canonical ordering of collections

Deterministic math where feasible

Explicit documentation where bitwise determinism cannot be guaranteed

4.2 Threat: LLM-Induced Drift

Examples:

LLM choosing execution paths

Prompt changes affecting runtime behavior

Model updates changing outputs

Mitigations:

LLMs prohibited from controlling execution flow

LLM outputs treated as offline-generated artifacts

Runtime must not call LLMs unless explicitly sandboxed and logged

4.3 Threat: State Leakage

Examples:

Global variables

Cached objects

Singleton services

Implicit memory in libraries

Mitigations:

No global mutable state

Step isolation

Explicit dependency injection

State hash verification between steps

4.4 Threat: Irreproducible External Dependencies

Examples:

Live web access

External APIs

Databases

Hardware-dependent behavior

Mitigations:

Offline-first default

External I/O must be explicitly declared

External data must be snapshotted or mocked

Artifacts must be hash-verified

4.5 Threat: Ledger Tampering or Incompleteness

Examples:

Missing steps

Partial logs

Undocumented failures

Mitigations:

Ledger written append-only

Ledger schema validation

Mandatory state hash checkpoints

Run invalidation if ledger is incomplete

5. Explicit Non-Threats (Out of Scope)

Determinant does not attempt to defend against:

Malicious runtime modification

Host OS compromise

Hardware-level nondeterminism beyond documented limits

Adversarial model weights

These are deployment concerns, not runtime concerns.

6. Design Consequences (Intentional Tradeoffs)

This design implies:

Reduced flexibility

Higher upfront structure

Fewer “wow” demos

Slower iteration for unstructured tasks

In exchange, it provides:

Trust

Auditability

Explainability

Operational survivability

This is intentional.

7. Design Enforcement

Violations of these principles should result in:

Failing tests

Explicit runtime errors

Rejection of contributions

Silent degradation is unacceptable.

8. Final Principle

If an execution cannot be explained to a skeptical engineer with a diff and a ledger, it does not belong in Determinant.

This document is the north star.
