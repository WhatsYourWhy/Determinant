"""Run orchestration for Determinant."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.metadata
import inspect
import platform
from pathlib import Path
import sys
import traceback
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
    config_data: dict[str, Any] = field(default_factory=dict)


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
    output_root = Path(config.output_dir)
    run_dir = output_root / "runs" / run_id
    state_dir = run_dir / "state"
    artifacts_dir = run_dir / "artifacts"
    meta_dir = run_dir / "meta"
    state_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    ledger_path = run_dir / "ledger.ndjson"
    manifest_path = run_dir / "manifest.json"
    ledger = LedgerWriter(str(ledger_path), run_id)

    config_payload = dict(config.config_data)
    config_payload.pop("output_dir", None)

    graph_payload = {
        "graph_id": graph.graph_id,
        "version": graph.version,
        "nodes": [
            {
                "node_id": f"n{index:04d}",
                "step_id": step.step_id,
            }
            for index, step in enumerate(graph.steps)
        ],
        "edges": [
            {"from": f"n{index:04d}", "to": f"n{index + 1:04d}"}
            for index in range(len(graph.steps) - 1)
        ],
    }
    graph_bytes = canonical_json_bytes(graph_payload)
    graph_path = meta_dir / "graph.json"
    graph_path.write_bytes(graph_bytes)
    graph_info = {
        "path": str(graph_path.relative_to(run_dir)),
        "sha256": sha256_bytes(graph_bytes),
    }

    config_bytes = canonical_json_bytes(config_payload)
    config_path = meta_dir / "config.json"
    config_path.write_bytes(config_bytes)
    config_info = {
        "path": str(config_path.relative_to(run_dir)),
        "sha256": sha256_bytes(config_bytes),
    }

    packages_by_name: dict[str, dict[str, str]] = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name") or dist.metadata.get("name") or dist.name
        if not name:
            continue
        normalized = name.strip()
        key = normalized.casefold()
        if key in packages_by_name:
            continue
        packages_by_name[key] = {"name": normalized, "version": dist.version}
    packages = sorted(packages_by_name.values(), key=lambda item: item["name"].casefold())
    env_payload = {
        "schema": "determinant.env.v0",
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "dependencies": {"type": "pip", "packages": packages},
    }
    env_bytes = canonical_json_bytes(env_payload)
    env_path = meta_dir / "env.json"
    env_path.write_bytes(env_bytes)
    env_info = {
        "path": str(env_path.relative_to(run_dir)),
        "sha256": sha256_bytes(env_bytes),
    }

    initial_state_hash = initial_state.sha256()
    initial_state_path = state_dir / "0000.json"
    initial_state.to_file(str(initial_state_path))

    try:
        runtime_version = importlib.metadata.version("determinant")
    except importlib.metadata.PackageNotFoundError:
        runtime_version = "unknown"

    ledger.write_run_start(
        {
            "runtime": {"name": "determinant", "version": runtime_version},
            "run": {"mode": "execute", "seed": config.seed},
            "inputs": {
                "graph": graph_info,
                "config": config_info,
                "env": env_info,
                "initial_state": {
                    "path": str(initial_state_path.relative_to(run_dir)),
                    "sha256": initial_state_hash,
                },
            },
        }
    )

    steps_manifest: list[dict[str, Any]] = []
    artifact_manifest: list[dict[str, Any]] = []
    current_state = initial_state
    current_state_path = initial_state_path
    run_failed = False
    failure_info: dict[str, Any] | None = None

    step_config = config.config_data
    for index, step in enumerate(graph.steps):
        step_info = {
            "index": index,
            "step_id": step.step_id,
            "step_version": _step_version(step),
            "graph_node_id": f"n{index:04d}",
        }
        state_in_info = {
            "path": str(current_state_path.relative_to(run_dir)),
            "sha256": current_state.sha256(),
        }

        ledger.write_step_start({"step": step_info, "state_in": state_in_info})
        try:
            result = step.execute(current_state, step_config, config.seed)
        except Exception as exc:  # noqa: BLE001 - run failures must be captured
            run_failed = True
            failure_info = _failure_payload(
                exc, {"index": index, "step_id": step.step_id}
            )
            ledger.write_run_fail(
                {
                    "status": "FAILED",
                    "failed_step": failure_info["failed_step"],
                    "error": failure_info["error"],
                }
            )
            steps_manifest.append(
                {
                    "step": step_info,
                    "state_in": state_in_info,
                    "events": [],
                    "artifacts": [],
                    "status": "FAILED",
                    "error": failure_info["error"],
                }
            )
            break

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
            suffix = Path(artifact.path).suffix
            artifact_name = f"{artifact.artifact_id}{suffix}"
            artifact_path = artifacts_dir / artifact_name
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(artifact.bytes)
            artifact_info = {
                "artifact_id": artifact.artifact_id,
                "logical_name": artifact.logical_name,
                "media_type": artifact.media_type,
                "path": str(artifact_path.relative_to(run_dir)),
                "sha256": sha256_bytes(artifact.bytes),
                "size_bytes": len(artifact.bytes),
            }
            artifacts_payload.append(artifact_info)
            artifact_manifest.append(artifact_info)
            ledger.write_artifact_written({"step": step_info, "artifact": artifact_info})

        state_out_hash = result.state.sha256()
        state_out_path = state_dir / f"{index + 1:04d}.json"
        result.state.to_file(str(state_out_path))
        state_out_info = {
            "path": str(state_out_path.relative_to(run_dir)),
            "sha256": state_out_hash,
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

    manifest = {
        "run_id": run_id,
        "graph": {"graph_id": graph.graph_id, "version": graph.version},
        "inputs": {
            "graph": graph_info,
            "config": config_info,
            "env": env_info,
            "initial_state": {
                "path": str(initial_state_path.relative_to(run_dir)),
                "sha256": initial_state_hash,
            },
            "seed": config.seed,
        },
        "steps": steps_manifest,
        "artifacts": artifact_manifest,
    }

    if run_failed:
        manifest["status"] = "FAILED"
        if failure_info:
            manifest["failed_step"] = failure_info["failed_step"]
            manifest["error"] = failure_info["error"]
    else:
        final_state_info = {
            "path": str(current_state_path.relative_to(run_dir)),
            "sha256": current_state.sha256(),
        }
        ledger.write_run_end(
            {
                "status": "COMPLETED",
                "final_state": final_state_info,
                "rollup": {
                    "steps_ok": len(graph.steps),
                    "steps_failed": 0,
                    "artifacts": len(artifact_manifest),
                },
            }
        )
        manifest["final_state"] = final_state_info
        manifest["status"] = "COMPLETED"
    ledger_bytes = ledger_path.read_bytes()
    manifest["ledger_sha256"] = sha256_bytes(ledger_bytes)
    if ledger._last_hash is not None:
        manifest["chain_head_hash"] = ledger._last_hash
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    return RunResult(
        run_id=run_id,
        final_state=None if run_failed else current_state,
        status="FAILED" if run_failed else "COMPLETED",
        ledger_path=str(ledger_path),
    )


def _step_version(step: Any) -> str:
    module = inspect.getmodule(step.__class__)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return "src:unknown"
    path = Path(module_file)
    if not path.exists():
        return "src:unknown"
    return f"src:{sha256_bytes(path.read_bytes())}"


def _failure_payload(exc: BaseException, step_info: dict[str, Any]) -> dict[str, Any]:
    trace = []
    for frame in traceback.extract_tb(exc.__traceback__):
        trace.append(
            {
                "file": str(Path(frame.filename).as_posix()),
                "line": frame.lineno,
                "function": frame.name,
            }
        )
    error = {
        "exc_type": exc.__class__.__name__,
        "code": exc.__class__.__name__,
        "message": str(exc),
    }
    if trace:
        error["trace"] = trace
    return {"failed_step": step_info, "error": error}
