"""Engine-independent agent loop implementing the four control operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .actions import ControlDecision, ControlOperation, WorldAction
from .base import Observation, PlayworldEngine


DecisionPolicy = Callable[[Observation, WorldAction, int], ControlDecision]


@dataclass(frozen=True)
class ActionResult:
    index: int
    planned: WorldAction
    executed: WorldAction | None
    decision: ControlDecision


class SharedActionController:
    """Apply keep, stop, extend, and correct decisions consistently."""

    def __init__(self, engine: PlayworldEngine, policy: DecisionPolicy):
        self.engine = engine
        self.policy = policy

    def run(self, plan: Sequence[WorldAction]) -> list[ActionResult]:
        results: list[ActionResult] = []
        for index, planned in enumerate(plan):
            observation = self.engine.observe()
            decision = self.policy(observation, planned, index)
            executed = resolve_decision(planned, decision)
            if decision.operation is ControlOperation.STOP_ACTION:
                self.engine.release_all()
                results.append(ActionResult(index, planned, None, decision))
                break

            if executed is None:
                raise RuntimeError("Controller produced no executable action")
            self.engine.perform(executed)
            results.append(ActionResult(index, planned, executed, decision))
        return results


def keep_all_policy(_: Observation, __: WorldAction, ___: int) -> ControlDecision:
    return ControlDecision(ControlOperation.KEEP_ACTION, reason="use benchmark plan")


def resolve_decision(
    planned: WorldAction, decision: ControlDecision
) -> WorldAction | None:
    if decision.operation is ControlOperation.STOP_ACTION:
        return None
    if decision.operation is ControlOperation.KEEP_ACTION:
        return planned
    if decision.operation is ControlOperation.EXTEND_ACTION:
        return WorldAction(
            key=planned.key,
            duration_ms=planned.duration_ms + decision.extension_ms,
        )
    if decision.operation is ControlOperation.CORRECT_ACTION:
        return decision.corrected_action
    raise ValueError(f"Unsupported operation: {decision.operation}")
