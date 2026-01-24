from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "determinant"))

from determinant.run import RunConfig, run
from determinant.state import State
from determinant.step import Artifact, Step, StepEvent, StepResult
from determinant.json_canonical import canonical_json_bytes


@dataclass
class ExampleGraph:
    graph_id: str
    version: str
    steps: list[Step]


class ParseDocuments(Step):
    def execute(self, state: State) -> StepResult:
        documents = state.data["documents"]
        parsed = [
            {"id": doc["id"], "text": doc["text"], "word_count": len(doc["text"].split())}
            for doc in documents
        ]
        new_state = State({"documents": documents, "parsed": parsed})
        event = StepEvent(
            event_type="INFO",
            code="DOCS_PARSED",
            message=f"Parsed {len(parsed)} documents",
            data={"doc_count": len(parsed)},
        )
        return StepResult(state=new_state, events=[event], artifacts=[])


class ScoreDocuments(Step):
    def __init__(self, weight: int) -> None:
        super().__init__()
        self.weight = weight

    def execute(self, state: State) -> StepResult:
        parsed = state.data["parsed"]
        scored = [
            {
                **doc,
                "score": int(doc["word_count"]) * self.weight,
            }
            for doc in parsed
        ]
        new_state = State({"documents": state.data["documents"], "parsed": parsed, "scored": scored})
        event = StepEvent(
            event_type="INFO",
            code="DOCS_SCORED",
            message=f"Scored {len(scored)} documents",
            data={"doc_count": len(scored), "weight": self.weight},
        )
        return StepResult(state=new_state, events=[event], artifacts=[])


class SelectDocuments(Step):
    def __init__(self, threshold: int) -> None:
        super().__init__()
        self.threshold = threshold

    def execute(self, state: State) -> StepResult:
        scored = state.data["scored"]
        selected = [doc for doc in scored if int(doc["score"]) >= self.threshold]
        new_state = State({
            "documents": state.data["documents"],
            "parsed": state.data["parsed"],
            "scored": scored,
            "selected": selected,
        })
        artifact = Artifact(
            artifact_id="selected-docs",
            logical_name="selected_documents",
            media_type="application/json",
            path="selected.json",
            bytes=canonical_json_bytes({"selected": selected}),
        )
        event = StepEvent(
            event_type="INFO",
            code="DOCS_SELECTED",
            message=f"Selected {len(selected)} documents",
            data={"selected": len(selected), "threshold": self.threshold},
        )
        return StepResult(state=new_state, events=[event], artifacts=[artifact])


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def _build_graph(graph_config: dict, config: dict) -> ExampleGraph:
    step_factories = {
        "parse_documents": lambda: ParseDocuments(),
        "score_documents": lambda: ScoreDocuments(config["score_weight"]),
        "select_documents": lambda: SelectDocuments(config["score_threshold"]),
    }
    steps: list[Step] = []
    for step_config in graph_config["steps"]:
        step_type = step_config["type"]
        step = step_factories[step_type]()
        step.step_id = step_config["step_id"]
        steps.append(step)
    return ExampleGraph(
        graph_id=graph_config["graph_id"],
        version=graph_config["version"],
        steps=steps,
    )


def _run_replay(graph: ExampleGraph, state: State, config: dict, label: str) -> Path:
    output_dir = Path(__file__).resolve().parent / "runs" / label
    run_config = RunConfig(
        run_id="document-replay",
        seed=config["seed"],
        output_dir=str(output_dir),
        config_data=config,
    )
    result = run(graph=graph, initial_state=state, config=run_config)
    return Path(result.ledger_path).parent


def main() -> None:
    example_dir = Path(__file__).resolve().parent
    graph_config = _load_json(example_dir / "graph.json")
    config = _load_json(example_dir / "config.json")
    initial_state = State.from_file(example_dir / "input_state.json")

    graph = _build_graph(graph_config, config)

    run_one = _run_replay(graph, initial_state, config, "first")
    run_two = _run_replay(graph, initial_state, config, "second")

    ledger_one = (run_one / "ledger.ndjson").read_bytes()
    ledger_two = (run_two / "ledger.ndjson").read_bytes()
    manifest_one = _load_json(run_one / "manifest.json")
    manifest_two = _load_json(run_two / "manifest.json")

    if ledger_one == ledger_two and manifest_one["final_state"]["sha256"] == manifest_two["final_state"]["sha256"]:
        print("Deterministic replay verified for document pipeline.")
    else:
        raise SystemExit("Replay mismatch detected.")


if __name__ == "__main__":
    main()
