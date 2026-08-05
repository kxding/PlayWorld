"""Fault-tolerant task harness with screenshots, decisions, and durable results."""

from __future__ import annotations

import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .actions import ControlDecision, ControlOperation, WorldAction, parse_action_sequence
from .base import Observation, PlayworldEngine
from .controller import DecisionPolicy, resolve_decision
from .recording import RunRecorder, retry_call, utc_now


@dataclass(frozen=True)
class HarnessConfig:
    connect_attempts: int = 3
    generation_attempts: int = 3
    observation_attempts: int = 3
    policy_attempts: int = 3
    retry_delay_seconds: float = 1.0
    natural_end_wait_seconds: float = 2.0
    policy_failure_fallback: str = "stop"

    def __post_init__(self) -> None:
        if self.policy_failure_fallback not in {"stop", "keep", "fail"}:
            raise ValueError("policy_failure_fallback must be stop, keep, or fail")
        for value in (
            self.connect_attempts,
            self.generation_attempts,
            self.observation_attempts,
            self.policy_attempts,
        ):
            if value < 1:
                raise ValueError("attempt counts must be at least 1")


class AgentHarness:
    def __init__(
        self,
        engine: PlayworldEngine,
        policy: DecisionPolicy,
        output_root: Path,
        config: HarnessConfig | None = None,
    ):
        self.engine = engine
        self.policy = policy
        self.output_root = output_root
        self.config = config or HarnessConfig()

    def _observe(self, recorder: RunRecorder, operation: str) -> Observation:
        return retry_call(
            operation,
            self.engine.observe,
            attempts=self.config.observation_attempts,
            delay_seconds=self.config.retry_delay_seconds,
            recorder=recorder,
        )

    def _policy_decision(
        self,
        recorder: RunRecorder,
        observation: Observation,
        planned: WorldAction,
        index: int,
    ) -> ControlDecision:
        try:
            return retry_call(
                f"policy_step_{index:03d}",
                lambda: self.policy(observation, planned, index),
                attempts=self.config.policy_attempts,
                delay_seconds=self.config.retry_delay_seconds,
                recorder=recorder,
            )
        except Exception as error:
            fallback = self.config.policy_failure_fallback
            recorder.event(
                "policy_fallback",
                action_index=index,
                fallback=fallback,
                error=str(error),
            )
            if fallback == "keep":
                return ControlDecision(
                    ControlOperation.KEEP_ACTION,
                    reason=f"policy failed; configured keep fallback: {error}",
                )
            if fallback == "stop":
                return ControlDecision(
                    ControlOperation.STOP_ACTION,
                    reason=f"policy failed; safe stop fallback: {error}",
                )
            raise

    def run_task(self, task: dict[str, Any], image: Path) -> dict[str, Any]:
        task_id = str(task["task_id"])
        recorder = RunRecorder(self.output_root, task_id)
        actions = parse_action_sequence(task["action_sequence_steps"])
        screenshots: dict[str, str] = {}
        action_results: list[dict[str, Any]] = []
        started_at = utc_now()
        status = "failed"
        error_record = None

        recorder.write_json("task.json", task)
        recorder.write_json("run_config.json", asdict(self.config))
        recorder.event("run_started", task_id=task_id, image=str(image))

        def recover_connection(_: Exception, __: int) -> None:
            self.engine.close()

        def recover_generation(_: Exception, __: int) -> None:
            self.engine.recover()

        try:
            retry_call(
                "connect",
                self.engine.connect,
                attempts=self.config.connect_attempts,
                delay_seconds=self.config.retry_delay_seconds,
                recorder=recorder,
                recover=recover_connection,
            )
            probe = self._observe(recorder, "probe_observation")
            screenshots["probe"] = recorder.screenshot("probe.jpg", probe.screenshot)

            retry_call(
                "upload_and_generate",
                lambda: self.engine.upload_and_generate(image, str(task["prompt"])),
                attempts=self.config.generation_attempts,
                delay_seconds=self.config.retry_delay_seconds,
                recorder=recorder,
                recover=recover_generation,
            )
            generated = self._observe(recorder, "generated_observation")
            screenshots["after_upload"] = recorder.screenshot(
                "after_upload.jpg", generated.screenshot
            )
            screenshots["before_actions"] = recorder.screenshot(
                "before_actions.jpg", generated.screenshot
            )
            recorder.event("world_ready", action_count=len(actions))

            stopped = False
            for index, planned in enumerate(actions):
                before = self._observe(recorder, f"before_action_{index:03d}")
                before_path = recorder.screenshot(
                    f"action_{index:03d}_before.jpg", before.screenshot
                )
                decision = self._policy_decision(
                    recorder, before, planned, index
                )
                executed = resolve_decision(planned, decision)
                recorder.event(
                    "decision",
                    action_index=index,
                    planned=planned,
                    decision=decision,
                    before_screenshot=before_path,
                    policy_trace=getattr(self.policy, "last_trace", None),
                )

                item = {
                    "index": index,
                    "planned": planned,
                    "decision": decision,
                    "executed": executed,
                    "before_screenshot": before_path,
                    "after_screenshot": None,
                    "status": "stopped" if executed is None else "pending",
                    "started_at": utc_now(),
                    "completed_at": None,
                }
                if executed is None:
                    self.engine.release_all()
                    item["completed_at"] = utc_now()
                    action_results.append(item)
                    stopped = True
                    recorder.event("actions_stopped", action_index=index)
                    break

                # Never blindly repeat an action after an ambiguous partial
                # execution. perform() guarantees key release; any failure is
                # recorded and stops the run for state safety.
                try:
                    self.engine.perform(executed)
                except Exception as action_error:
                    self.engine.release_all()
                    item["status"] = "failed"
                    item["error"] = {
                        "type": type(action_error).__name__,
                        "message": str(action_error),
                    }
                    item["completed_at"] = utc_now()
                    action_results.append(item)
                    recorder.event(
                        "action_failed", action_index=index, error=str(action_error)
                    )
                    raise

                after = self._observe(recorder, f"after_action_{index:03d}")
                after_path = recorder.screenshot(
                    f"action_{index:03d}_after.jpg", after.screenshot
                )
                item["after_screenshot"] = after_path
                item["status"] = "completed"
                item["completed_at"] = utc_now()
                action_results.append(item)
                recorder.event(
                    "action_completed",
                    action_index=index,
                    executed=executed,
                    after_screenshot=after_path,
                )

            after_actions = self._observe(recorder, "after_actions_observation")
            screenshots["after_actions"] = recorder.screenshot(
                "after_actions.jpg", after_actions.screenshot
            )
            if self.config.natural_end_wait_seconds > 0:
                time.sleep(self.config.natural_end_wait_seconds)
            natural_end = self._observe(recorder, "natural_end_observation")
            screenshots["natural_end"] = recorder.screenshot(
                "natural_end.jpg", natural_end.screenshot
            )
            status = "stopped" if stopped else "completed"
        except Exception as error:
            error_record = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }
            recorder.event("run_failed", error=error_record)
        finally:
            try:
                self.engine.release_all()
            finally:
                self.engine.close()

        result = {
            "task_id": task_id,
            "source_task_id": task.get("source_task_id"),
            "status": status,
            "started_at": started_at,
            "completed_at": utc_now(),
            "run_dir": str(recorder.run_dir),
            "image": str(image),
            "screenshots": screenshots,
            "planned_action_count": len(actions),
            "processed_action_count": len(action_results),
            "actions": action_results,
            "error": error_record,
        }
        recorder.write_json("result.json", result)
        recorder.event("run_finished", status=status)
        return result
