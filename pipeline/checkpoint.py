"""체크포인트 저장/복원 — 실패 시 해당 단계부터 재개"""

import json
from dataclasses import asdict
from pathlib import Path
from pipeline.context import PipelineContext


class CheckpointManager:
    def __init__(self, output_dir: str):
        self.path = Path(output_dir) / "checkpoint.json"
        self._completed_steps = []  # 메모리에 누적 관리

    def save(self, ctx: PipelineContext, completed_step: str):
        data = asdict(ctx)

        if not completed_step.startswith("FAILED:"):
            if completed_step not in self._completed_steps:
                self._completed_steps.append(completed_step)

        data["_completed_steps"] = list(self._completed_steps)
        data["_failed_step"] = completed_step if completed_step.startswith("FAILED:") else ""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self) -> tuple[PipelineContext | None, list[str]]:
        if not self.path.exists():
            return None, []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        completed = data.pop("_completed_steps", [])
        data.pop("_failed_step", None)

        # 메모리에도 복원
        self._completed_steps = list(completed)

        try:
            ctx = PipelineContext(**data)
        except TypeError:
            return None, []
        return ctx, completed

    def clear(self):
        self._completed_steps = []
        if self.path.exists():
            self.path.unlink()
