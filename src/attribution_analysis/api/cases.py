"""归因公共内核 HTTP 接口。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from attribution_analysis.api.authentication import SubjectContext, current_subject, require_permission

from attribution_analysis.application.core import (
    CaseConflictError,
    CaseNotFoundError,
    CreateCaseCommand,
    FollowUpCommand,
    case_summary,
    evidence_payload,
    execution_payload,
    plan_payload,
    result_payload,
    runtime_log_payload,
    task_payload,
)
from attribution_analysis.domain.core import AttributionResult, Evidence, EvidenceClass, new_id, utc_now
from attribution_analysis.infrastructure.composition import build_core_service, open_database_by_url


router = APIRouter(prefix="/api/v1", tags=["attribution"])
service = build_core_service()


class CreateCaseRequest(BaseModel):
    conversation_id: str = Field(min_length=1)
    question: str = Field(min_length=5, max_length=2000)
    scenario_hint: str | None = None


class FollowUpRequest(BaseModel):
    question: str = Field(min_length=5, max_length=2000)


def run_case_background(case_id: str, subject_id: str) -> None:
    """后台执行入口；失败已由 CoreService 持久化为失败状态。"""
    try:
        service.execute_case(case_id, subject_id)
    except Exception:
        return


def run_follow_up_background(case_id: str, subject_id: str, question: str, idempotency_key: str) -> None:
    """后台追问执行入口；幂等键已由 register_follow_up 注册，force=True 强制执行一次。"""
    try:
        service.follow_up(
            case_id,
            FollowUpCommand(
                subject_id=subject_id,
                question=question,
                idempotency_key=idempotency_key,
            ),
            force=True,
        )
    except Exception:
        return


def request_id() -> str:
    """本地请求标识（无分布式追踪时固定值）。"""
    return "local-request"


def envelope(data: object) -> dict[str, object]:
    """标准响应信封：request_id + data。"""
    return {"request_id": request_id(), "data": data}


@router.post("/cases", status_code=status.HTTP_202_ACCEPTED)
def create_case(
    payload: CreateCaseRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    subject: SubjectContext = Depends(require_permission("cases:write")),
) -> dict[str, object]:
    """创建归因 Case（幂等键必填），返回摘要；命中幂等时标记 reused。"""
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key is required")
    try:
        case, reused = service.create_case(
            CreateCaseCommand(
                subject_id=subject.subject_id,
                conversation_id=payload.conversation_id,
                question=payload.question,
                scenario_hint=payload.scenario_hint,
                idempotency_key=idempotency_key,
            ),
            execute=False,
        )
    except CaseConflictError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    response = envelope(case_summary(case))
    if reused:
        response["reused"] = True
    else:
        background_tasks.add_task(run_case_background, case.case_id, subject.subject_id)
    return response



@router.get("/cases")
def list_all_cases(
    conversation_id: str | None = Query(default=None),
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """按当前主体列出全部 Case；可选按会话筛选。"""
    return envelope([case_summary(case) for case in service.list_cases(subject.subject_id, conversation_id)])


@router.get("/conversations/{conversation_id}/cases")
def list_cases(
    conversation_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """按会话列出当前主体的 Case 摘要。"""
    return envelope([case_summary(case) for case in service.list_cases(subject.subject_id, conversation_id)])


@router.get("/cases/{case_id}")
def get_case(
    case_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """读取单个 Case 摘要（主体隔离）。"""
    try:
        case = service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return envelope(case_summary(case))


@router.get("/cases/{case_id}/task")
def get_task(
    case_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """读取 Case 的任务进度状态。"""
    try:
        case = service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return envelope(task_payload(case))


@router.get("/cases/{case_id}/task-logs")
def get_task_logs(
    case_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """读取 Case 的去敏运行日志。"""
    try:
        logs = service.task_logs(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return envelope([runtime_log_payload(log) for log in logs])


@router.get("/cases/{case_id}/events")
async def case_events(
    case_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> StreamingResponse:
    """以 SSE 输出当前 Case 的阶段快照；客户端断线后可从持久化状态继续恢复。"""
    def snapshot() -> dict[str, object]:
        case = service.get_case(case_id, subject.subject_id)
        executions = [execution_payload(item, tuple(case.evidence)) for item in case.executions]
        return {
            "case": case_summary(case),
            "plan": plan_payload(case.plans[-1]) if case.plans else None,
            "executions": executions,
            "results": [result_payload(item) for item in case.results],
            "attachments": [],
        }

    async def event_stream():
        emitted: set[str] = set()
        for _ in range(120):
            try:
                current = snapshot()
            except CaseNotFoundError:
                yield f"event: error\\ndata: {json.dumps({'detail': 'case not found'}, ensure_ascii=False)}\\n\\n"
                return
            case_data = current["case"]
            plan = current["plan"]
            executions = current["executions"]
            results = current["results"]
            events: list[tuple[str, object]] = [("case", case_data)]
            if plan:
                events.append(("plan", plan))
            for execution in executions:
                events.append(("execution", execution))
            for result in results:
                events.append(("result", result))
            for kind, payload in events:
                event_id = f"{kind}:{payload.get('execution_id') or payload.get('result_id') or payload.get('plan_id') or payload.get('case_id')}"
                if event_id in emitted:
                    continue
                emitted.add(event_id)
                yield f"event: {kind}\\ndata: {json.dumps(payload, ensure_ascii=False)}\\n\\n"
            if case_data["status"] in {"completed", "degraded", "dependency_error", "failed", "cancelled", "rejected"}:
                yield f"event: done\\ndata: {json.dumps({'status': case_data['status']}, ensure_ascii=False)}\\n\\n"
                return
            yield ": heartbeat\\n\\n"
            await asyncio.sleep(0.5)
        yield "event: error\\ndata: {\"detail\":\"event stream timeout\"}\\n\\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cases/{case_id}/plans/{version_no}")
def get_plan(
    case_id: str,
    version_no: int,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """读取指定版本的执行计划。"""
    try:
        case = service.get_case(case_id, subject.subject_id)
        plan = next(item for item in case.plans if item.version_no == version_no)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="plan not found") from exc
    return envelope(plan_payload(plan))


@router.get("/cases/{case_id}/executions")
def get_executions(
    case_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """读取 Case 的工具执行记录及其证据引用。"""
    try:
        case = service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    evidence = tuple(case.evidence)
    return envelope([execution_payload(item, evidence) for item in case.executions])


@router.get("/cases/{case_id}/evidence")
def get_evidence(
    case_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """读取 Case 的全部证据（含来源等级）。"""
    try:
        case = service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return envelope([evidence_payload(item) for item in case.evidence])


@router.get("/cases/{case_id}/results")
def get_results(
    case_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """读取 Case 的结果版本列表。"""
    try:
        case = service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return envelope([result_payload(item) for item in case.results])


@router.post("/cases/{case_id}/follow-ups", status_code=status.HTTP_202_ACCEPTED)
def follow_up(
    case_id: str,
    payload: FollowUpRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    subject: SubjectContext = Depends(require_permission("cases:write")),
) -> dict[str, object]:
    """对 Case 发起追问（幂等键必填），注册后立即返回，由后台任务生成新版本结果。"""
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key is required")
    try:
        case = service.register_follow_up(
            case_id,
            FollowUpCommand(
                subject_id=subject.subject_id,
                question=payload.question,
                idempotency_key=idempotency_key,
            ),
        )
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    except CaseConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    background_tasks.add_task(
        run_follow_up_background,
        case.case_id,
        subject.subject_id,
        payload.question,
        idempotency_key,
    )
    return envelope(case_summary(case))


@router.post("/cases/{case_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_case(
    case_id: str,
    subject: SubjectContext = Depends(require_permission("cases:write")),
) -> dict[str, object]:
    """取消 Case（幂等，证据保留）。"""
    try:
        case = service.cancel(case_id, subject.subject_id, "user_requested")
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return envelope(case_summary(case))

