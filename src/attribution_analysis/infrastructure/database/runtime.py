"""Case 运行态的可恢复存储。

该存储只保存 Case 聚合快照；业务 MySQL 仍由 NL2SQL 适配器只读访问。
"""

from __future__ import annotations

import json
from typing import Any

from attribution_analysis.application.runtime_logs import RuntimeLog, record_runtime_event
from attribution_analysis.domain.core import (
    AnalysisPlan,
    AttributionCase,
    AttributionResult,
    CaseStatus,
    Evidence,
    EvidenceClass,
    ExecutionStatus,
    StateTransition,
    TaskStatus,
    ToolExecution,
)


class PersistentCaseStore:
    """使用项目数据库保存完整聚合快照，重启后可恢复。"""

    def __init__(self, connection) -> None:
        self.connection = connection
        self.cases: dict[str, AttributionCase] = {}
        self.task_logs: dict[str, list[RuntimeLog]] = {}
        self.idempotency: dict[tuple[str, str, str, str], str] = {}
        self.follow_up_idempotency: dict[tuple[str, str], str] = {}
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS attribution_case_snapshots (
                case_id VARCHAR PRIMARY KEY,
                subject_id VARCHAR NOT NULL,
                conversation_id VARCHAR NOT NULL,
                input_fingerprint VARCHAR NOT NULL,
                idempotency_key VARCHAR NOT NULL,
                aggregate_json TEXT NOT NULL,
                updated_at VARCHAR NOT NULL,
                UNIQUE(subject_id, conversation_id, input_fingerprint, idempotency_key)
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS attribution_case_logs (
                case_id VARCHAR NOT NULL,
                event VARCHAR NOT NULL,
                task_status VARCHAR NOT NULL,
                message VARCHAR NOT NULL,
                occurred_at VARCHAR NOT NULL
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS attribution_follow_up_idempotency (
                case_id VARCHAR NOT NULL,
                idempotency_key VARCHAR NOT NULL,
                PRIMARY KEY(case_id, idempotency_key)
            )"""
        )
        self.connection.commit()
        self._load()

    def _load(self) -> None:
        rows = self.connection.execute(
            "SELECT aggregate_json FROM attribution_case_snapshots"
        ).fetchall()
        for (payload,) in rows:
            case = _case_from_dict(json.loads(payload))
            self.cases[case.case_id] = case
            self.task_logs.setdefault(case.case_id, [])
            self.idempotency[(case.subject_id, case.conversation_id, case.input_fingerprint, case.idempotency_key)] = case.case_id
        for row in self.connection.execute("SELECT case_id, event, task_status, message, occurred_at FROM attribution_case_logs ORDER BY occurred_at").fetchall():
            case_id, event, task_status, message, occurred_at = row
            self.task_logs.setdefault(case_id, []).append(RuntimeLog(case_id, event, task_status, message, occurred_at))
        for case_id, idempotency_key in self.connection.execute("SELECT case_id, idempotency_key FROM attribution_follow_up_idempotency").fetchall():
            self.follow_up_idempotency[(case_id, idempotency_key)] = case_id

    def _refresh_case(self, case_id: str) -> AttributionCase | None:
        row = self.connection.execute(
            "SELECT aggregate_json FROM attribution_case_snapshots WHERE case_id = ?",
            [case_id],
        ).fetchone()
        if row is None:
            self.cases.pop(case_id, None)
            return None
        case = _case_from_dict(json.loads(row[0]))
        self.cases[case.case_id] = case
        self.idempotency[(case.subject_id, case.conversation_id, case.input_fingerprint, case.idempotency_key)] = case.case_id
        return case

    def _refresh_all(self) -> None:
        persisted_ids = {row[0] for row in self.connection.execute("SELECT case_id FROM attribution_case_snapshots").fetchall()}
        for case_id in tuple(self.cases):
            if case_id not in persisted_ids:
                self.cases.pop(case_id, None)
        for case_id in persisted_ids:
            self._refresh_case(case_id)

    def find_by_idempotency(self, subject_id: str, conversation_id: str, input_fingerprint: str, idempotency_key: str) -> AttributionCase | None:
        self._refresh_all()
        case_id = self.idempotency.get((subject_id, conversation_id, input_fingerprint, idempotency_key))
        return self.cases.get(case_id) if case_id else None

    def get(self, case_id: str, subject_id: str) -> AttributionCase | None:
        case = self._refresh_case(case_id)
        return case if case and case.subject_id == subject_id else None

    def list(self, subject_id: str, conversation_id: str | None = None) -> tuple[AttributionCase, ...]:
        self._refresh_all()
        cases = tuple(case for case in self.cases.values() if case.subject_id == subject_id)
        if conversation_id:
            cases = tuple(case for case in cases if case.conversation_id == conversation_id)
        return tuple(sorted(cases, key=lambda case: case.created_at, reverse=True))

    def logs(self, case_id: str, subject_id: str) -> tuple[RuntimeLog, ...]:
        if self.get(case_id, subject_id) is None:
            return ()
        rows = self.connection.execute(
            "SELECT case_id, event, task_status, message, occurred_at FROM attribution_case_logs WHERE case_id = ? ORDER BY occurred_at",
            [case_id],
        ).fetchall()
        records = [RuntimeLog(*row) for row in rows]
        self.task_logs[case_id] = records
        return tuple(records)

    def register_follow_up(self, case_id: str, idempotency_key: str) -> bool:
        key = (case_id, idempotency_key)
        if key in self.follow_up_idempotency or self.connection.execute(
            "SELECT 1 FROM attribution_follow_up_idempotency WHERE case_id = ? AND idempotency_key = ?",
            [case_id, idempotency_key],
        ).fetchone():
            self.follow_up_idempotency[key] = case_id
            return False
        try:
            self.connection.execute(
                "INSERT INTO attribution_follow_up_idempotency (case_id, idempotency_key) VALUES (?, ?)",
                [case_id, idempotency_key],
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        self.follow_up_idempotency[key] = case_id
        return True

    def append_log(self, case_id: str, event: str, task_status: TaskStatus) -> None:
        records = list(self.logs(case_id, self.cases.get(case_id, None).subject_id)) if case_id in self.cases else []
        record_runtime_event(records, case_id=case_id, event=event, task_status=task_status)
        record = records[-1]
        try:
            self.connection.execute(
                "INSERT INTO attribution_case_logs (case_id, event, task_status, message, occurred_at) VALUES (?, ?, ?, ?, ?)",
                [record.case_id, record.event, record.task_status, record.message, record.occurred_at],
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        self.task_logs[case_id] = records


    def discard(self, case_id: str) -> None:
        case = self.cases.get(case_id)
        try:
            self.connection.execute("DELETE FROM attribution_case_snapshots WHERE case_id = ?", [case_id])
            self.connection.execute("DELETE FROM attribution_case_logs WHERE case_id = ?", [case_id])
            self.connection.execute("DELETE FROM attribution_follow_up_idempotency WHERE case_id = ?", [case_id])
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        self.cases.pop(case_id, None)
        self.task_logs.pop(case_id, None)
        if case:
            self.idempotency.pop((case.subject_id, case.conversation_id, case.input_fingerprint, case.idempotency_key), None)
        self.follow_up_idempotency = {key: value for key, value in self.follow_up_idempotency.items() if value != case_id}

    def save(self, case: AttributionCase) -> None:
        payload = json.dumps(_case_to_dict(case), ensure_ascii=False, separators=(",", ":"))
        try:
            self.connection.execute(
                "DELETE FROM attribution_case_snapshots WHERE case_id = ?",
                [case.case_id],
            )
            self.connection.execute(
                """INSERT INTO attribution_case_snapshots
                   (case_id, subject_id, conversation_id, input_fingerprint, idempotency_key, aggregate_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [case.case_id, case.subject_id, case.conversation_id, case.input_fingerprint, case.idempotency_key, payload, case.created_at],
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        self.cases[case.case_id] = case
        self.idempotency[(case.subject_id, case.conversation_id, case.input_fingerprint, case.idempotency_key)] = case.case_id
        self.task_logs.setdefault(case.case_id, [])


def _case_to_dict(case: AttributionCase) -> dict[str, Any]:
    return {
        "case_id": case.case_id, "subject_id": case.subject_id, "conversation_id": case.conversation_id,
        "question": case.question, "scenario_hint": case.scenario_hint, "input_fingerprint": case.input_fingerprint,
        "idempotency_key": case.idempotency_key, "status": case.status.value, "cancel_reason": case.cancel_reason,
        "created_at": case.created_at,
        "plans": [{"plan_id": p.plan_id, "case_id": p.case_id, "version_no": p.version_no, "steps": list(p.steps), "current_step_no": p.current_step_no, "max_steps": p.max_steps} for p in case.plans],
        "executions": [{"execution_id": e.execution_id, "case_id": e.case_id, "plan_id": e.plan_id, "step_no": e.step_no, "tool_name": e.tool_name, "status": e.status.value, "input_fingerprint": e.input_fingerprint, "started_at": e.started_at, "finished_at": e.finished_at, "error_class": e.error_class, "duration_ms": e.duration_ms, "details": e.details} for e in case.executions],
        "evidence": [{"evidence_id": e.evidence_id, "case_id": e.case_id, "execution_id": e.execution_id, "source_class": e.source_class.value, "source_ref": e.source_ref, "rule_version": e.rule_version, "content_summary": e.content_summary, "recorded_at": e.recorded_at} for e in case.evidence],
        "results": [{"result_id": r.result_id, "case_id": r.case_id, "version_no": r.version_no, "status": r.status, "question": r.question, "key_metrics": list(r.key_metrics), "conclusion": r.conclusion, "missing_items": list(r.missing_items), "manual_review_required": r.manual_review_required, "evidence_ids": list(r.evidence_ids), "created_at": r.created_at} for r in case.results],
        "transitions": [{"from_status": t.from_status.value, "to_status": t.to_status.value, "occurred_at": t.occurred_at} for t in case.transitions],
    }


def _case_from_dict(data: dict[str, Any]) -> AttributionCase:
    return AttributionCase(
        case_id=data["case_id"], subject_id=data["subject_id"], conversation_id=data["conversation_id"], question=data["question"],
        scenario_hint=data.get("scenario_hint"), input_fingerprint=data["input_fingerprint"], idempotency_key=data["idempotency_key"],
        status=CaseStatus(data["status"]), plans=[AnalysisPlan(p["plan_id"], p["case_id"], p["version_no"], tuple(p["steps"]), p["current_step_no"], p["max_steps"]) for p in data["plans"]],
        executions=[ToolExecution(e["execution_id"], e["case_id"], e["plan_id"], e["step_no"], e["tool_name"], ExecutionStatus(e["status"]), e["input_fingerprint"], e["started_at"], e["finished_at"], e.get("error_class"), e.get("duration_ms", 0), e.get("details", {})) for e in data["executions"]],
        evidence=[Evidence(e["evidence_id"], e["case_id"], e["execution_id"], EvidenceClass(e["source_class"]), e["source_ref"], e["rule_version"], e["content_summary"], e["recorded_at"]) for e in data["evidence"]],
        results=[AttributionResult(r["result_id"], r["case_id"], r["version_no"], r["status"], r["question"], tuple(r["key_metrics"]), r["conclusion"], tuple(r["missing_items"]), r["manual_review_required"], tuple(r["evidence_ids"]), r["created_at"]) for r in data["results"]],
        transitions=[StateTransition(CaseStatus(t["from_status"]), CaseStatus(t["to_status"]), t["occurred_at"]) for t in data["transitions"]],
        cancel_reason=data.get("cancel_reason"), created_at=data["created_at"],
    )
