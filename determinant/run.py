"""Run orchestration for Determinant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ledger import LedgerWriter
from .hashing import sha256_bytes
from .json_canonical import canonical_json_bytes

from .graph import Graph
from .state import State


@dataclass
class RunConfig:
    """Runtime configuration for a Determinant run."""

    run_id: str | None
    seed: int
    output_dir: str
    config_data: dict[str, Any]


@dataclass
class RunResult:
    """Result metadata for a Determinant run."""

    run_id: str
    final_state: State | None
    status: str
    ledger_path: str


def run(graph: Graph, initial_state: State, config: RunConfig) -> RunResult:
    """Execute a graph with the provided state."""
    run_id = config.run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    run_dir = Path(config.output_dir)
    state_dir = run_dir / "state"
    artifacts_dir = run_dir / "artifacts"
    state_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = run_dir / "ledger.ndjson"
    manifest_path = run_dir / "manifest.json"
    ledger = LedgerWriter(str(ledger_path), run_id)

    initial_state_path = state_dir / "initial.json"
    initial_state.to_file(str(initial_state_path))

    config_payload = {
        key: value for key, value in config.config_data.items() if key != "output_dir"
    }

    ledger.write_run_start(
        {
            "runtime": {"seed": config.seed},
            "run": {"graph_id": graph.graph_id, "graph_version": graph.version},
            "inputs": {
                "initial_state": {
                    "path": str(initial_state_path.relative_to(run_dir)),
                    "sha256": initial_state.sha256(),
                },
                "config": config_payload,
            },
        }
    )

    steps_manifest: list[dict[str, Any]] = []
    artifact_manifest: list[dict[str, Any]] = []
    current_state = initial_state
    current_state_path = initial_state_path

    for index, step in enumerate(graph.steps, start=1):
        step_info = {"index": index, "step_id": step.step_id}
        state_in_info = {
            "path": str(current_state_path.relative_to(run_dir)),
            "sha256": current_state.sha256(),
        }

        ledger.write_step_start({"step": step_info, "state_in": state_in_info})

        result = step.execute(current_state)

        events_payload = []
        for event in result.events:
            event_payload = {
                "event_type": event.event_type,
                "code": event.code,
                "message": event.message,
                "data": event.data,
            }
            events_payload.append(event_payload)
            ledger.write_step_event({"step": step_info, "event": event_payload})

        artifacts_payload = []
        for artifact in result.artifacts:
            artifact_path = artifacts_dir / f"step_{index}" / artifact.path
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(artifact.bytes)
            artifact_info = {
                "artifact_id": artifact.artifact_id,
                "logical_name": artifact.logical_name,
                "media_type": artifact.media_type,
                "path": str(artifact_path.relative_to(run_dir)),
                "sha256": sha256_bytes(artifact.bytes),
            }
            artifacts_payload.append(artifact_info)
            artifact_manifest.append(artifact_info)
            ledger.write_artifact_written({"step": step_info, "artifact": artifact_info})

        state_out_path = state_dir / f"step_{index}_out.json"
        result.state.to_file(str(state_out_path))
        state_out_info = {
            "path": str(state_out_path.relative_to(run_dir)),
            "sha256": result.state.sha256(),
        }

        ledger.write_step_end(
            {"step": step_info, "status": "COMPLETED", "state_out": state_out_info}
        )

        steps_manifest.append(
            {
                "step": step_info,
                "state_in": state_in_info,
                "state_out": state_out_info,
                "events": events_payload,
                "artifacts": artifacts_payload,
                "status": "COMPLETED",
            }
        )

        current_state = result.state
        current_state_path = state_out_path

    final_state_info = {
        "path": str(current_state_path.relative_to(run_dir)),
        "sha256": current_state.sha256(),
    }

    ledger.write_run_end(
        {
            "status": "COMPLETED",
            "final_state": final_state_info,
            "rollup": {
                "steps": len(graph.steps),
                "artifacts": len(artifact_manifest),
            },
        }
    )

    manifest = {
        "run_id": run_id,
        "graph": {"graph_id": graph.graph_id, "version": graph.version},
        "inputs": {
            "initial_state": {
                "path": str(initial_state_path.relative_to(run_dir)),
                "sha256": initial_state.sha256(),
            },
            "config": config_payload,
            "seed": config.seed,
        },
        "steps": steps_manifest,
        "artifacts": artifact_manifest,
        "final_state": final_state_info,
        "status": "COMPLETED",
    }
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    return RunResult(
        run_id=run_id,
        final_state=current_state,
        status="COMPLETED",
        ledger_path=str(ledger_path),
    )
