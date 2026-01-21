"""Run orchestration for deterministic execution."""

from __future__ import annotations

import dataclasses
import platform
import sys
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ledger import LedgerWriter
from .state import State
from .step import Artifact, Step, StepEvent
from .utils.hashing import sha256_hexdigest
from .utils.json_canonical import canonical_json_bytes

RUNTIME_NAME = "determinant"
RUNTIME_VERSION = "0.1.0"


@dataclass
class RunConfig:
    """Configuration inputs for a run."""

    run_id: str | None = None
    seed: int = 0
    output_dir: str = "runs"
    mode: str = "execute"
    created_by: str = "api"
    command: str | None = None
    config_data: Mapping[str, Any] = field(default_factory=dict)

    def meta_dict(self) -> dict[str, Any]:
        data = dict(self.config_data)
        data.update(
            {
                "seed": self.seed,
                "mode": self.mode,
                "created_by": self.created_by,
            }
        )
        if self.command is not None:
            data["command"] = self.command
        return data


@dataclass
class RunResult:
    """Return value for run execution."""

    run_id: str
    final_state: State | None
    status: str
    ledger_path: str


def run(graph: Any, initial_state: State, config: RunConfig | Mapping[str, Any]) -> RunResult:
    """Execute a deterministic graph run and persist ledger/state/artifacts."""

    run_config = _normalize_config(config)
    run_id = run_config.run_id or uuid.uuid4().hex
    run_dir = Path(run_config.output_dir) / run_id
    meta_dir = run_dir / "meta"
    state_dir = run_dir / "state"
    artifacts_dir = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=False)
    meta_dir.mkdir(parents=True, exist_ok=False)
    state_dir.mkdir(parents=True, exist_ok=False)
    artifacts_dir.mkdir(parents=True, exist_ok=False)

    graph_payload = _graph_to_dict(graph)
    graph_path = meta_dir / "graph.json"
    graph_sha = _write_canonical_json(graph_path, graph_payload)

    config_payload = run_config.meta_dict()
    config_path = meta_dir / "config.json"
    config_sha = _write_canonical_json(config_path, config_payload)

    env_payload = _environment_payload()
    env_path = meta_dir / "env.json"
    env_sha = _write_canonical_json(env_path, env_payload)

    initial_state_path, initial_state_sha = _snapshot_state(
        initial_state, state_dir, 0
    )

    ledger_path = run_dir / "ledger.ndjson"
    manifest_path = run_dir / "manifest.json"

    artifacts_manifest: list[dict[str, Any]] = []
    step_manifest: list[dict[str, Any]] = []
    steps_ok = 0
    steps_failed = 0
    artifact_count = 0
    last_record: dict[str, Any] | None = None
    current_state = initial_state
    current_state_path = initial_state_path

    with LedgerWriter(ledger_path, run_id) as ledger:
        last_record = ledger.write_record(
            "RUN_START",
            {
                "runtime": {"name": RUNTIME_NAME, "version": RUNTIME_VERSION},
                "run": _run_payload(run_config),
                "inputs": {
                    "graph": {"path": _relpath(graph_path, run_dir), "sha256": graph_sha},
                    "config": {"path": _relpath(config_path, run_dir), "sha256": config_sha},
                    "env": {"path": _relpath(env_path, run_dir), "sha256": env_sha},
                    "initial_state": {
                        "path": current_state_path,
                        "sha256": initial_state_sha,
                    },
                },
            },
        )

        status = "OK"
        final_state: State | None = None
        for index, step in enumerate(_graph_steps(graph)):
            step_version = _step_version(step)
            step_payload = _step_payload(index, step, step_version, graph)
            state_in_sha = current_state.sha256()
            state_in_path = current_state_path
            last_record = ledger.write_record(
                "STEP_START",
                {
                    "step": step_payload,
                    "state_in": {"path": state_in_path, "sha256": state_in_sha},
                },
            )
            try:
                result = step.execute(current_state)
            except Exception as exc:
                status = "FAILED"
                steps_failed += 1
                last_record = ledger.write_record(
                    "RUN_FAIL",
                    {
                        "status": status,
                        "step": {"index": index, "step_id": step.step_id},
                        "error": _error_payload(exc),
                    },
                )
                break

            _emit_step_events(ledger, index, step, result.events)
            artifact_results = _write_artifacts(artifacts_dir, run_dir, result.artifacts)
            for artifact_payload in artifact_results:
                last_record = ledger.write_record(
                    "ARTIFACT_WRITTEN",
                    {
                        "step": {"index": index, "step_id": step.step_id},
                        "artifact": artifact_payload,
                    },
                )
                artifacts_manifest.append(artifact_payload)
                artifact_count += 1

            current_state = result.state
            state_path, state_sha = _snapshot_state(current_state, state_dir, index + 1)
            current_state_path = state_path
            last_record = ledger.write_record(
                "STEP_END",
                {
                    "step": {"index": index, "step_id": step.step_id},
                    "status": "OK",
                    "state_out": {"path": state_path, "sha256": state_sha},
                },
            )
            steps_ok += 1
            step_manifest.append(
                {
                    "step_id": step.step_id,
                    "step_version": step_version,
                    "state_in": {"path": state_in_path, "sha256": state_in_sha},
                    "state_out": {"path": state_path, "sha256": state_sha},
                    "status": "OK",
                }
            )
            final_state = current_state

        if status == "OK":
            final_state = current_state
            last_record = ledger.write_record(
                "RUN_END",
                {
                    "status": "OK",
                    "final_state": {
                        "path": current_state_path,
                        "sha256": current_state.sha256(),
                    },
                    "rollup": {
                        "steps_ok": steps_ok,
                        "steps_failed": steps_failed,
                        "artifacts": artifact_count,
                    },
                },
            )

    manifest_payload = {
        "run_id": run_id,
        "ledger_sha256": sha256_hexdigest(ledger_path.read_bytes()),
        "chain_head_hash": last_record["hash"] if last_record else None,
        "inputs": {
            "graph": {"path": _relpath(graph_path, run_dir), "sha256": graph_sha},
            "config": {"path": _relpath(config_path, run_dir), "sha256": config_sha},
            "env": {"path": _relpath(env_path, run_dir), "sha256": env_sha},
            "initial_state": {"path": initial_state_path, "sha256": initial_state_sha},
        },
        "final_state": (
            {"path": current_state_path, "sha256": current_state.sha256()}
            if status == "OK"
            else None
        ),
        "artifacts": artifacts_manifest,
        "steps": step_manifest,
        "rollup": {
            "steps_ok": steps_ok,
            "steps_failed": steps_failed,
            "artifacts": artifact_count,
        },
        "status": status,
    }
    _write_canonical_json(manifest_path, manifest_payload)

    return RunResult(
        run_id=run_id,
        final_state=final_state if status == "OK" else None,
        status=status,
        ledger_path=str(ledger_path),
    )


def _normalize_config(config: RunConfig | Mapping[str, Any]) -> RunConfig:
    if isinstance(config, RunConfig):
        return config
    run_id = config.get("run_id")
    seed = config.get("seed", 0)
    output_dir = config.get("output_dir", "runs")
    mode = config.get("mode", "execute")
    created_by = config.get("created_by", "api")
    command = config.get("command")
    config_data = {
        key: value
        for key, value in config.items()
        if key
        not in {
            "run_id",
            "seed",
            "output_dir",
            "mode",
            "created_by",
            "command",
        }
    }
    return RunConfig(
        run_id=run_id,
        seed=seed,
        output_dir=output_dir,
        mode=mode,
        created_by=created_by,
        command=command,
        config_data=config_data,
    )


def _graph_to_dict(graph: Any) -> dict[str, Any]:
    if hasattr(graph, "to_dict"):
        data = graph.to_dict()
        if not isinstance(data, Mapping):
            raise TypeError("graph.to_dict() must return a mapping")
        return dict(data)
    if dataclasses.is_dataclass(graph):
        data = {
            field.name: getattr(graph, field.name)
            for field in dataclasses.fields(graph)
            if field.name != "steps"
        }
        if hasattr(graph, "steps"):
            data["steps"] = [{"step_id": step.step_id} for step in _graph_steps(graph)]
        return data
    steps = _graph_steps(graph)
    return {
        "graph_id": getattr(graph, "graph_id", "graph"),
        "version": getattr(graph, "version", "v0"),
        "steps": [{"step_id": step.step_id} for step in steps],
    }


def _graph_steps(graph: Any) -> Sequence[Step]:
    steps = getattr(graph, "steps", None)
    if steps is None:
        raise AttributeError("graph must expose a steps sequence")
    return list(steps)


def _run_payload(config: RunConfig) -> dict[str, Any]:
    payload = {
        "mode": config.mode,
        "seed": config.seed,
        "created_by": config.created_by,
    }
    if config.command is not None:
        payload["command"] = config.command
    return payload


def _environment_payload() -> dict[str, Any]:
    try:
        import importlib.metadata as metadata
    except ImportError:  # pragma: no cover
        metadata = None
    packages: list[dict[str, str]] = []
    if metadata is not None:
        packages = [
            {"name": dist.metadata["Name"], "version": dist.version}
            for dist in metadata.distributions()
            if dist.metadata.get("Name") and dist.version
        ]
        packages.sort(key=lambda item: item["name"].lower())
    return {
        "schema": "determinant.env.v0",
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "dependencies": {
            "packages": packages,
        },
    }


def _snapshot_state(state: State, state_dir: Path, index: int) -> tuple[str, str]:
    sha = state.sha256()
    filename = f"{index:04d}_{sha}.json"
    path = state_dir / filename
    state.to_file(path)
    return f"state/{filename}", sha


def _step_version(step: Step) -> str:
    module = sys.modules.get(step.__class__.__module__, None)
    source_path = getattr(module, "__file__", None)
    if source_path is None:
        return "src:unknown"
    path = Path(source_path)
    if path.suffix == ".pyc":
        candidate = path.with_suffix(".py")
        if candidate.exists():
            path = candidate
    try:
        data = path.read_bytes()
    except OSError:
        return "src:unknown"
    return f"src:{sha256_hexdigest(data)}"


def _step_payload(index: int, step: Step, step_version: str, graph: Any) -> dict[str, Any]:
    payload = {
        "index": index,
        "step_id": step.step_id,
        "step_version": step_version,
    }
    graph_node_id = getattr(step, "graph_node_id", None)
    if graph_node_id is None:
        graph_node_id = getattr(graph, "node_id_by_step", {}).get(step.step_id)
    if graph_node_id is not None:
        payload["graph_node_id"] = graph_node_id
    return payload


def _emit_step_events(
    ledger: LedgerWriter, index: int, step: Step, events: Sequence[StepEvent]
) -> None:
    for event in events:
        ledger.write_record(
            "STEP_EVENT",
            {
                "step": {"index": index, "step_id": step.step_id},
                "event": {
                    "event_type": event.event_type,
                    "code": event.code,
                    "message": event.message,
                    "data": event.data,
                },
            },
        )


def _write_artifacts(
    artifacts_dir: Path,
    run_dir: Path,
    artifacts: Sequence[Artifact],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for artifact in artifacts:
        filename = _artifact_filename(artifact)
        path = artifacts_dir / filename
        path.write_bytes(artifact.bytes)
        sha = sha256_hexdigest(artifact.bytes)
        payloads.append(
            {
                "artifact_id": artifact.artifact_id,
                "logical_name": artifact.logical_name,
                "media_type": artifact.media_type,
                "path": _relpath(path, run_dir),
                "sha256": sha,
                "size_bytes": len(artifact.bytes),
            }
        )
    return payloads


def _artifact_filename(artifact: Artifact) -> str:
    path = Path(artifact.path)
    suffix = path.suffix or _media_type_extension(artifact.media_type)
    return f"{artifact.artifact_id}{suffix}"


def _media_type_extension(media_type: str) -> str:
    mapping = {
        "application/json": ".json",
        "text/plain": ".txt",
        "application/octet-stream": ".bin",
    }
    return mapping.get(media_type, ".bin")


def _write_canonical_json(path: Path, payload: Mapping[str, Any]) -> str:
    data = canonical_json_bytes(payload)
    path.write_bytes(data)
    return sha256_hexdigest(data)


def _relpath(path: Path, run_dir: Path) -> str:
    return path.relative_to(run_dir).as_posix()


def _error_payload(exc: Exception) -> dict[str, Any]:
    return {
        "type": exc.__class__.__name__,
        "message": str(exc),
        "trace": _sanitize_traceback(exc),
    }


def _sanitize_traceback(exc: Exception) -> list[str]:
    frames = traceback.extract_tb(exc.__traceback__)
    return [f"{frame.filename}:{frame.lineno}:{frame.name}" for frame in frames]
