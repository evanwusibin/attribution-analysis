"""公共内核用例服务；外部数据能力通过可替换工具边界进入。"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from typing import Any

from attribution_analysis.application.runtime_logs import RuntimeLog, record_runtime_event
from attribution_analysis.application.scenarios.workbench import BusinessScenarioRunner, ScenarioProjection
from attribution_analysis.application.tools.evidence import EvidenceToolset
from attribution_analysis.ports.cases import CaseRepository
from attribution_analysis.ports.llm import LLMMessage, LLMPort
from attribution_analysis.domain.core import (
    AnalysisPlan,
    AttributionCase,
    AttributionResult,
    CaseStatus,
    Evidence,
    EvidenceClass,
    ExecutionStatus,
    TaskStatus,
    ToolExecution,
    fingerprint,
    new_id,
    task_status_from_case,
    utc_now,
)


class CaseNotFoundError(LookupError):
    pass


class CaseConflictError(ValueError):
    pass


SCENARIO_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("S2", ("索赔", "理赔", "三包", "保修", "工时费")),
    ("S1", ("故障", "报码", "报错", "无法启动", "异响", "诊断")),
    ("E1", ("丢单", "流失", "战败", "未成交")),
    ("E2", ("业绩", "达成", "销量", "销售额", "目标")),
)


def infer_scenario(question: str) -> str | None:
    """仅选择已有专项投影；未命中时保留通用双路归因。"""
    normalized = question.casefold()
    return next((scenario for scenario, keywords in SCENARIO_KEYWORDS if any(keyword in normalized for keyword in keywords)), None)


@dataclass(frozen=True)
class CreateCaseCommand:
    subject_id: str
    conversation_id: str
    question: str
    idempotency_key: str
    scenario_hint: str | None = None


@dataclass(frozen=True)
class FollowUpCommand:
    subject_id: str
    question: str
    idempotency_key: str


class InMemoryCaseStore:
    """可替换的运行域存储；不承担外部业务主数据职责。"""

    def __init__(self) -> None:
        """初始化空的内存存储（cases/task_logs/幂等键表）。"""
        self.cases: dict[str, AttributionCase] = {}
        self.task_logs: dict[str, list[RuntimeLog]] = {}
        self.idempotency: dict[tuple[str, str, str, str], str] = {}
        self.follow_up_idempotency: dict[tuple[str, str], str] = {}

    def find_by_idempotency(self, subject_id: str, conversation_id: str, input_fingerprint: str, idempotency_key: str) -> AttributionCase | None:
        case_id = self.idempotency.get((subject_id, conversation_id, input_fingerprint, idempotency_key))
        return self.cases.get(case_id) if case_id else None

    def get(self, case_id: str, subject_id: str) -> AttributionCase | None:
        case = self.cases.get(case_id)
        return case if case and case.subject_id == subject_id else None

    def list(self, subject_id: str, conversation_id: str | None = None) -> tuple[AttributionCase, ...]:
        cases = tuple(case for case in self.cases.values() if case.subject_id == subject_id)
        if conversation_id:
            cases = tuple(case for case in cases if case.conversation_id == conversation_id)
        return tuple(sorted(cases, key=lambda case: case.created_at, reverse=True))

    def save(self, case: AttributionCase) -> None:
        self.cases[case.case_id] = case
        self.task_logs.setdefault(case.case_id, [])
        self.idempotency[(case.subject_id, case.conversation_id, case.input_fingerprint, case.idempotency_key)] = case.case_id

    def logs(self, case_id: str, subject_id: str) -> tuple[RuntimeLog, ...]:
        if self.get(case_id, subject_id) is None:
            return ()
        return tuple(self.task_logs.setdefault(case_id, []))

    def register_follow_up(self, case_id: str, idempotency_key: str) -> bool:
        key = (case_id, idempotency_key)
        if key in self.follow_up_idempotency:
            return False
        self.follow_up_idempotency[key] = case_id
        return True

    def append_log(self, case_id: str, event: str, task_status: TaskStatus) -> None:
        record_runtime_event(self.task_logs.setdefault(case_id, []), case_id=case_id, event=event, task_status=task_status)
    def discard(self, case_id: str) -> None:
        case = self.cases.pop(case_id, None)
        self.task_logs.pop(case_id, None)
        if case:
            self.idempotency.pop((case.subject_id, case.conversation_id, case.input_fingerprint, case.idempotency_key), None)


class CoreService:
    """Case 生命周期用例编排：创建/执行/追问/取消/证据投影。"""

    def __init__(
        self,
        evidence_toolset: EvidenceToolset,
        store: CaseRepository | None = None,
        scenario_runner: BusinessScenarioRunner | None = None,
        llm: LLMPort | None = None,
    ) -> None:
        """装配证据工具集、可选存储与场景投影器。"""
        self.evidence_toolset = evidence_toolset
        self.store = store or InMemoryCaseStore()
        self.scenario_runner = scenario_runner
        self.llm = llm

    def create_case(self, command: CreateCaseCommand, *, execute: bool = True) -> tuple[AttributionCase, bool]:
        """创建归因 Case 并立即执行。

        幂等保证：相同 subject + conversation + 问题指纹 + 幂等键 只创建一个 Case。
        返回 (case, reused)，reused=True 表示命中幂等。
        """
        if len(command.question.strip()) < 5:
            raise CaseConflictError("question must contain at least 5 characters")
        if command.scenario_hint and command.scenario_hint not in {"E1", "E2", "E3", "E4", "E5", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"}:
            raise CaseConflictError("scenario must be one of E1-E5 or S1-S8")
        resolved_scenario = command.scenario_hint or infer_scenario(command.question)
        input_hash = fingerprint(command.question, resolved_scenario or "")
        existing = self.store.find_by_idempotency(command.subject_id, command.conversation_id, input_hash, command.idempotency_key)
        if existing:
            return existing, True

        case = AttributionCase(
            case_id=new_id("case"),
            subject_id=command.subject_id,
            conversation_id=command.conversation_id,
            question=command.question,
            scenario_hint=resolved_scenario,
            input_fingerprint=input_hash,
            idempotency_key=command.idempotency_key,
        )
        self.store.save(case)
        try:
            self._record_task_event(case, "case.queued")
            if execute:
                self._run_case(case, version_no=1)
            self.store.save(case)
        except Exception:
            self.store.discard(case.case_id)
            raise
        return case, False

    def execute_case(self, case_id: str, subject_id: str) -> AttributionCase:
        """执行已入队的 Case；后台任务失败时保留 Case 和失败审计。"""
        case = self.get_case(case_id, subject_id)
        if case.plans or case.results:
            return case
        try:
            self._run_case(case, version_no=1)
            self.store.save(case)
        except Exception as exc:
            if case.status in {CaseStatus.EXECUTING, CaseStatus.SYNTHESIZING}:
                case.transition(CaseStatus.FAILED)
            self._record_task_event(case, "case.failed")
            self.store.save(case)
            raise exc
        return case

    def register_follow_up(self, case_id: str, command: FollowUpCommand) -> AttributionCase:
        """仅注册追问幂等键并校验状态，不执行；返回当前 Case。

        追问真正执行由后台任务调用 follow_up(force=True) 完成。幂等键在此注册，
        用于拦截重复 POST；后台任务通过 force=True 跳过幂等检查强制执行一次。
        """
        case = self.get_case(case_id, command.subject_id)
        if case.status not in {CaseStatus.COMPLETED, CaseStatus.NEEDS_INPUT, CaseStatus.FAILED, CaseStatus.CANCELLED}:
            raise CaseConflictError("case state does not allow follow-up")
        self.store.register_follow_up(case_id, command.idempotency_key)
        return case

    def follow_up(self, case_id: str, command: FollowUpCommand, *, force: bool = False) -> AttributionCase:
        """对已完成的 Case 发起追问，生成新版本的 Plan 和 Result。

        默认行为：幂等键已注册（无论 register_follow_up 还是本方法）则直接返回当前 Case，
        确保重复调度不重复执行。后台任务应传 force=True 强制执行已注册的追问。
        """
        case = self.get_case(case_id, command.subject_id)
        if case.status not in {CaseStatus.COMPLETED, CaseStatus.NEEDS_INPUT, CaseStatus.FAILED, CaseStatus.CANCELLED}:
            raise CaseConflictError("case state does not allow follow-up")
        if not force:
            if not self.store.register_follow_up(case_id, command.idempotency_key):
                return case
        original = deepcopy(case)
        try:
            self._run_case(case, version_no=len(case.plans) + 1, question=command.question)
            self.store.save(case)
        except Exception:
            restored = deepcopy(original)
            case.__dict__.clear()
            case.__dict__.update(restored.__dict__)
            self.store.save(case)
            raise
        return case

    def cancel(self, case_id: str, subject_id: str, reason: str) -> AttributionCase:
        """取消 Case：仅允许从可取消状态发起，取消后证据保留。"""
        case = self.get_case(case_id, subject_id)
        if case.status in {CaseStatus.COMPLETED, CaseStatus.NEEDS_INPUT, CaseStatus.FAILED, CaseStatus.CANCELLED, CaseStatus.REJECTED}:
            return case
        case.transition(CaseStatus.CANCELLING)
        case.cancel_reason = reason
        case.transition(CaseStatus.CANCELLED)
        self.store.save(case)
        return case

    def _persist(self, case: AttributionCase) -> None:
        """将运行态聚合提交到可选持久化存储；测试 fake 不需要实现。"""
        self.store.save(case)

    def get_case(self, case_id: str, subject_id: str) -> AttributionCase:
        """按 subject 隔离获取 Case；越权访问抛 CaseNotFoundError。"""
        case = self.store.get(case_id, subject_id)
        if not case:
            raise CaseNotFoundError(case_id)
        return case

    def list_cases(self, subject_id: str, conversation_id: str | None = None) -> tuple[AttributionCase, ...]:
        """列出当前 subject 的 Case，可按 conversation 过滤，按 case_id 倒序。"""
        return self.store.list(subject_id, conversation_id)

    def task_logs(self, case_id: str, subject_id: str) -> tuple[RuntimeLog, ...]:
        """读取 Case 的运行日志（脱敏后的事件流）。"""
        self.get_case(case_id, subject_id)
        return self.store.logs(case_id, subject_id)

    def append_evidence(self, case_id: str, subject_id: str, evidence: Evidence) -> AttributionCase:
        """将外部摄取产生的 Evidence 追加到主体拥有的 Case 并立即提交。"""
        case = self.get_case(case_id, subject_id)
        case.evidence.append(evidence)
        self.store.save(case)
        return case
    def _record_task_event(self, case: AttributionCase, event: str) -> None:
        """记录一次任务生命周期事件（queued/completed 等）到日志流。"""
        self.store.append_log(case.case_id, event, task_status_from_case(case.status))

    def _run_scenario(
        self,
        case: AttributionCase,
        question: str,
        plan: AnalysisPlan,
        step_no: int,
    ) -> tuple[list[Evidence], ScenarioProjection] | None:
        """执行场景投影（售后/售前专项诊断），返回生成的证据列表与投影。

        无场景 Runner 或场景不匹配时返回 None，回退到通用双路归因。
        """
        if self.scenario_runner is None:
            return None
        projection = self.scenario_runner.run(case.scenario_hint, question)
        if projection is None:
            return None
        execution = ToolExecution(
            execution_id=new_id("exec"),
            case_id=case.case_id,
            plan_id=plan.plan_id,
            step_no=step_no,
            tool_name="scenario_projection",
            status=ExecutionStatus.SUCCEEDED,
            input_fingerprint=fingerprint(question, case.scenario_hint or ""),
            started_at=utc_now(),
            finished_at=utc_now(),
            error_class=None,
            duration_ms=0,
            details={
                "scenario": case.scenario_hint,
                "conclusion": projection.conclusion,
                "key_metrics": list(projection.key_metrics),
                "missing_items": list(projection.missing_items),
                "evidence": [
                    {
                        "source_class": item.source_class,
                        "source_ref": item.source_ref,
                        "rule_version": item.rule_version,
                        "content_summary": item.content_summary,
                    }
                    for item in projection.evidence
                ],
                "manual_review_required": projection.manual_review_required,
            },
        )
        case.executions.append(execution)
        evidence = [
            Evidence(
                evidence_id=new_id("evidence"),
                case_id=case.case_id,
                execution_id=execution.execution_id,
                source_class=EvidenceClass(item.source_class),
                source_ref=item.source_ref,
                rule_version=item.rule_version,
                content_summary=item.content_summary,
                recorded_at=utc_now(),
            )
            for item in projection.evidence
        ]
        case.evidence.extend(evidence)
        return evidence, projection

    def _synthesize_with_llm(
        self,
        case: AttributionCase,
        plan: AnalysisPlan,
        question: str,
        evidence: list[Evidence],
        step_no: int,
    ) -> tuple[str | None, str | None]:
        """由 LLM 基于本 Case 证据形成候选结论；调用失败必须可审计。"""
        if self.llm is None:
            case.executions.append(ToolExecution(
                new_id("exec"), case.case_id, plan.plan_id, step_no,
                "synthesize_with_llm", ExecutionStatus.FAILED,
                fingerprint(question, "synthesize_with_llm"), utc_now(), utc_now(),
                error_class="LLMNotConfigured", duration_ms=0,
                details={
                    "backend": "unconfigured",
                    "called": False,
                    "status": "not_configured",
                    "error_type": "LLMNotConfigured",
                    "error_message": "未配置 LLM，未发起模型调用。",
                    "generated_text": None,
                    "evidence_ids": [item.evidence_id for item in evidence],
                },
            ))
            return None, "LLMNotConfigured"
        prompt = "\n".join(f"- [{item.source_class}] {item.content_summary}" for item in evidence)
        started = utc_now()
        try:
            response = self.llm.complete((
                LLMMessage("system", "你是归因分析助手。仅基于提供证据形成候选结论；明确不确定性，不作自动责任裁决。输出必须使用 Markdown 结构，依次包含以下小节：\n## 核心结论（1-2 句直接回答问题）\n## 关键要点（分点列出，每点在括号内注明所依据的证据等级 FACT/MOCK/MISSING）\n## 原因分析（按直接原因、间接原因分点，结合证据说明机理）\n## SWOT 分析（依次给出 优势、劣势、机会、威胁 四组，每组 1-3 点）\n## 注解与局限（数据缺失、不确定性、需人工复核的范围）\n禁止臆造未在证据中出现的数据；证据不足时如实标注。"),
                LLMMessage("user", f"问题：{question}\n证据：\n{prompt}"),
            ))
            execution = ToolExecution(new_id("exec"), case.case_id, plan.plan_id, step_no, "synthesize_with_llm", ExecutionStatus.SUCCEEDED, fingerprint(question, "synthesize_with_llm"), started, utc_now(), duration_ms=0, details={
                "backend": response.provider,
                "model": response.model,
                "called": True,
                "status": "completed",
                "generated_text": response.content,
                "evidence_ids": [item.evidence_id for item in evidence],
            })
            case.executions.append(execution)
            return response.content, None
        except Exception as exc:
            case.executions.append(ToolExecution(
                new_id("exec"), case.case_id, plan.plan_id, step_no,
                "synthesize_with_llm", ExecutionStatus.FAILED,
                fingerprint(question, "synthesize_with_llm"), started, utc_now(),
                error_class=type(exc).__name__, duration_ms=0,
                details={
                    "backend": "unavailable",
                    "called": True,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "generated_text": None,
                    "evidence_ids": [item.evidence_id for item in evidence],
                },
            ))
            return None, type(exc).__name__

    def _run_case(self, case: AttributionCase, version_no: int, question: str | None = None) -> None:
        """执行一次 Case 分析：规划 → 证据收集 → 场景投影 → 合成结果 → 完成。

        所有工具执行、证据、结果都会持久化到 Case，Result 只能引用本 Case 的 Evidence。
        """
        active_question = question or case.question
        if case.status in {CaseStatus.COMPLETED, CaseStatus.NEEDS_INPUT, CaseStatus.FAILED, CaseStatus.CANCELLED}:
            case.transition(CaseStatus.PLANNING)
        elif case.status == CaseStatus.CREATED:
            case.transition(CaseStatus.VALIDATING)
            case.transition(CaseStatus.PLANNING)
        plan = AnalysisPlan(
            new_id("plan"),
            case.case_id,
            version_no,
            ("query_business_data", "query_knowledge_base", "synthesize_result"),
        )
        case.plans.append(plan)
        case.transition(CaseStatus.EXECUTING)

        collected = self.evidence_toolset.collect(active_question)
        new_evidence: list[Evidence] = []
        for step_no, item in enumerate(collected, start=1):
            execution = ToolExecution(
                execution_id=new_id("exec"),
                case_id=case.case_id,
                plan_id=plan.plan_id,
                step_no=step_no,
                tool_name=item.tool_name,
                status=ExecutionStatus.FAILED if item.failure_class else ExecutionStatus.SUCCEEDED,
                input_fingerprint=fingerprint(active_question, item.tool_name),
                started_at=utc_now(),
                finished_at=utc_now(),
                error_class=item.failure_class,
                duration_ms=item.duration_ms,
                details=item.details,
            )
            case.executions.append(execution)
            evidence = Evidence(
                evidence_id=new_id("evidence"),
                case_id=case.case_id,
                execution_id=execution.execution_id,
                source_class=EvidenceClass(item.source_class),
                source_ref=item.source_ref,
                rule_version=item.rule_version,
                content_summary=item.content_summary,
                recorded_at=utc_now(),
            )
            case.evidence.append(evidence)
            new_evidence.append(evidence)

        scenario_projection = self._run_scenario(case, active_question, plan, len(collected) + 1)
        if scenario_projection:
            new_evidence.extend(scenario_projection[0])

        llm_conclusion, llm_failure = self._synthesize_with_llm(
            case, plan, active_question, new_evidence, len(collected) + (2 if scenario_projection else 1)
        )
        case.transition(CaseStatus.SYNTHESIZING)
        has_missing = any(item.source_class == EvidenceClass.MISSING for item in new_evidence)
        dependency_failed = bool(llm_failure) or any(
            execution.status in {ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT}
            for execution in case.executions
            if execution.plan_id == plan.plan_id
        )
        projection = scenario_projection[1] if scenario_projection else None
        result = AttributionResult(
            result_id=new_id("result"),
            case_id=case.case_id,
            version_no=version_no,
            status="dependency_error" if dependency_failed else ("degraded" if has_missing else "completed"),
            question=active_question,
            key_metrics=projection.key_metrics if projection else (),
            conclusion=(
                projection.conclusion
                if projection
                else (llm_conclusion or "候选结论未生成：LLM 依赖不可用，当前仅保留已获取的证据，需人工复核。")
            ),
            missing_items=(
                projection.missing_items
                if projection and projection.missing_items
                else ((f"LLM 结果合成失败：{llm_failure}。",) if llm_failure else (("存在不可用的数据源或知识库，需要补充后重新分析。",) if has_missing else ("候选结论基于当前 Case 的受控证据，仍需人工复核。",)))
            ),
            manual_review_required=True,
            evidence_ids=tuple(item.evidence_id for item in new_evidence),
            created_at=utc_now(),
        )
        case.results.append(result)
        case.transition(CaseStatus.FAILED if dependency_failed else CaseStatus.COMPLETED)
        self._record_task_event(case, "case.failed" if dependency_failed else "case.completed")


def case_summary(case: AttributionCase) -> dict[str, Any]:
    """Case 摘要载荷（HTTP 返回用）。"""
    return {
        "case_id": case.case_id,
        "conversation_id": case.conversation_id,
        "scenario_hint": case.scenario_hint,
        "question": case.question,
        "created_at": case.created_at,
        "status": case.status.value,
        "plan_version": len(case.plans),
        "result_version": len(case.results),
        "evidence_count": len(case.evidence),
        "manual_review_required": any(result.manual_review_required for result in case.results),
    }


def task_payload(case: AttributionCase) -> dict[str, str]:
    """任务进度载荷（HTTP 返回用）。"""
    return {"task_id": case.case_id, "status": task_status_from_case(case.status).value}


def runtime_log_payload(log: RuntimeLog) -> dict[str, str]:
    """运行日志载荷（去敏后）。"""
    return {
        "case_id": log.case_id,
        "event": log.event,
        "task_status": log.task_status,
        "message": log.message,
        "occurred_at": log.occurred_at,
    }


def evidence_payload(evidence: Evidence) -> dict[str, Any]:
    """证据载荷（带来源等级与定位）。"""
    return {
        "evidence_id": evidence.evidence_id,
        "execution_id": evidence.execution_id,
        "source_class": evidence.source_class.value,
        "source_ref": evidence.source_ref,
        "rule_version": evidence.rule_version,
        "content_summary": evidence.content_summary,
        "recorded_at": evidence.recorded_at,
    }


def execution_payload(execution: ToolExecution, evidence: tuple[Evidence, ...]) -> dict[str, Any]:
    """工具执行载荷（含该执行产生的证据 ID 列表）。"""
    return {
        "execution_id": execution.execution_id,
        "plan_id": execution.plan_id,
        "step_no": execution.step_no,
        "tool_name": execution.tool_name,
        "status": execution.status.value,
        "duration_ms": execution.duration_ms,
        "failure_class": execution.error_class,
        "details": execution.details,
        "evidence_ids": [item.evidence_id for item in evidence if item.execution_id == execution.execution_id],
        "started_at": execution.started_at,
        "finished_at": execution.finished_at,
    }


def plan_payload(plan: AnalysisPlan) -> dict[str, Any]:
    """分析计划载荷（含步骤与预算）。"""
    return {
        "plan_id": plan.plan_id,
        "case_id": plan.case_id,
        "version_no": plan.version_no,
        "steps": list(plan.steps),
        "current_step_no": plan.current_step_no,
        "max_steps": plan.max_steps,
    }


def result_payload(result: AttributionResult) -> dict[str, Any]:
    """结果载荷（含证据引用与人工复核标记）。"""
    return {
        "result_id": result.result_id,
        "version_no": result.version_no,
        "status": result.status,
        "question": result.question,
        "key_metrics": list(result.key_metrics),
        "conclusion": result.conclusion,
        "missing_items": list(result.missing_items),
        "manual_review_required": result.manual_review_required,
        "evidence_ids": list(result.evidence_ids),
        "created_at": result.created_at,
    }
