"""公共归因内核的领域数据结构与状态迁移。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any
from uuid import uuid4


class CaseStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    PLANNING = "planning"
    EXECUTING = "executing"
    SYNTHESIZING = "synthesizing"
    COMPLETED = "completed"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class EvidenceClass(StrEnum):
    FACT = "FACT"
    MOCK = "MOCK"
    MISSING = "MISSING"


class ExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


def task_status_from_case(status: CaseStatus) -> TaskStatus:
    """Derive platform task progress without introducing a second state owner."""
    return {
        CaseStatus.CREATED: TaskStatus.QUEUED,
        CaseStatus.VALIDATING: TaskStatus.QUEUED,
        CaseStatus.PLANNING: TaskStatus.QUEUED,
        CaseStatus.EXECUTING: TaskStatus.RUNNING,
        CaseStatus.SYNTHESIZING: TaskStatus.RUNNING,
        CaseStatus.CANCELLING: TaskStatus.RUNNING,
        CaseStatus.COMPLETED: TaskStatus.SUCCESS,
        CaseStatus.NEEDS_INPUT: TaskStatus.SUCCESS,
        CaseStatus.FAILED: TaskStatus.FAILED,
        CaseStatus.REJECTED: TaskStatus.FAILED,
        CaseStatus.CANCELLED: TaskStatus.CANCELLED,
    }[status]


@dataclass(frozen=True)
class StateTransition:
    from_status: CaseStatus
    to_status: CaseStatus
    occurred_at: str


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    case_id: str
    execution_id: str
    source_class: EvidenceClass
    source_ref: str
    rule_version: str
    content_summary: str
    recorded_at: str


@dataclass(frozen=True)
class ToolExecution:
    execution_id: str
    case_id: str
    plan_id: str
    step_no: int
    tool_name: str
    status: ExecutionStatus
    input_fingerprint: str
    started_at: str
    finished_at: str
    error_class: str | None = None
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisPlan:
    plan_id: str
    case_id: str
    version_no: int
    steps: tuple[str, ...]
    current_step_no: int = 0
    max_steps: int = 8


@dataclass(frozen=True)
class AttributionResult:
    result_id: str
    case_id: str
    version_no: int
    status: str
    question: str
    key_metrics: tuple[dict[str, Any], ...]
    conclusion: str
    missing_items: tuple[str, ...]
    manual_review_required: bool
    evidence_ids: tuple[str, ...]
    created_at: str


@dataclass
class AttributionCase:
    case_id: str
    subject_id: str
    conversation_id: str
    question: str
    scenario_hint: str | None
    input_fingerprint: str
    idempotency_key: str
    status: CaseStatus = CaseStatus.CREATED
    plans: list[AnalysisPlan] = field(default_factory=list)
    executions: list[ToolExecution] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    results: list[AttributionResult] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    cancel_reason: str | None = None
    created_at: str = field(default_factory=lambda: utc_now())

    def transition(self, target: CaseStatus) -> None:
        """执行 Case 状态迁移；非法迁移抛 ValueError 并记录转移历史。"""
        allowed = {
            CaseStatus.CREATED: {CaseStatus.VALIDATING},
            CaseStatus.VALIDATING: {CaseStatus.REJECTED, CaseStatus.PLANNING},
            CaseStatus.PLANNING: {CaseStatus.EXECUTING, CaseStatus.NEEDS_INPUT, CaseStatus.CANCELLING},
            CaseStatus.EXECUTING: {CaseStatus.SYNTHESIZING, CaseStatus.NEEDS_INPUT, CaseStatus.FAILED, CaseStatus.CANCELLING, CaseStatus.PLANNING},
            CaseStatus.SYNTHESIZING: {CaseStatus.COMPLETED, CaseStatus.NEEDS_INPUT, CaseStatus.FAILED},
            CaseStatus.COMPLETED: {CaseStatus.PLANNING},
            CaseStatus.NEEDS_INPUT: {CaseStatus.PLANNING},
            CaseStatus.FAILED: {CaseStatus.PLANNING},
            CaseStatus.CANCELLING: {CaseStatus.CANCELLED},
            CaseStatus.CANCELLED: {CaseStatus.PLANNING},
            CaseStatus.REJECTED: set(),
        }
        if target not in allowed[self.status]:
            raise ValueError(f"illegal case transition: {self.status} -> {target}")
        previous = self.status
        self.status = target
        self.transitions.append(StateTransition(previous, target, utc_now()))


def utc_now() -> str:
    """返回当前 UTC 时间的 ISO 字符串。"""
    return datetime.now(timezone.utc).isoformat()


def fingerprint(*values: str) -> str:
    """对若干字符串做 SHA-256 指纹（幂等键/去重用途）。"""
    return sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def new_id(prefix: str) -> str:
    """生成带前缀的唯一 ID。"""
    return f"{prefix}_{uuid4().hex}"

