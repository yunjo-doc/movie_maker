"""Pipeline + Step 기본 클래스"""

import logging
from abc import ABC, abstractmethod
from pipeline.context import PipelineContext
from pipeline.checkpoint import CheckpointManager

logger = logging.getLogger(__name__)


class Step(ABC):
    name: str = "unnamed"

    @abstractmethod
    def run(self, ctx: PipelineContext) -> PipelineContext:
        pass


class Pipeline:
    def __init__(self, steps: list[Step], checkpoint: CheckpointManager):
        self.steps = steps
        self.checkpoint = checkpoint

    def run(self, ctx: PipelineContext, resume: bool = False) -> PipelineContext:
        completed = []
        if resume:
            saved, completed = self.checkpoint.load()
            if saved:
                ctx = saved
                logger.info(f"체크포인트에서 재개. 완료된 단계: {completed}")

        for step in self.steps:
            if step.name in completed:
                logger.info(f"[SKIP] {step.name}")
                continue

            logger.info(f"{'='*50}")
            logger.info(f"[START] {step.name}")
            logger.info(f"{'='*50}")
            try:
                ctx = step.run(ctx)
                self.checkpoint.save(ctx, step.name)
                logger.info(f"[DONE] {step.name}")
            except Exception as e:
                logger.error(f"[FAIL] {step.name}: {e}")
                self.checkpoint.save(ctx, f"FAILED:{step.name}")
                raise

        self.checkpoint.clear()
        logger.info("파이프라인 완료!")
        return ctx
