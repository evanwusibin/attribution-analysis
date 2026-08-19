"""售后故障诊断 HTTP 接口（S4 · 电池包为首域）。

独立于归因公共内核路由：售后场景通过 `FaultDiagnosisService` 执行，
输出六段结构（问题/关键指标/结论/缺失清单/人工复核/证据）并复用证据分级。
公共内核不承载领域规则，领域规则全部位于 application/scenarios 与 tools。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.application.scenarios.after_sales import DiagnosisRequest, FaultDiagnosisService
from attribution_analysis.adapters.after_sales.demo import DemoAfterSalesAdapter
from attribution_analysis.infrastructure.composition import open_database_by_url


router = APIRouter(prefix="/api/v1/after-sales", tags=["after-sales"])


class DiagnosisRequestPayload(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    vin: str | None = None
    claim_id: str | None = None
    wo_id: str | None = None
    batch_id: str | None = None


def _service() -> FaultDiagnosisService:
    """按当前数据库 URL 装配售后诊断服务（演示适配器只读）。"""
    connection = open_database_by_url()
    return FaultDiagnosisService(DemoAfterSalesAdapter(connection))


def _evidence_items(outcome) -> list[dict[str, object]]:
    """把候选假设与缺失项投影为可审计的证据摘要。"""
    items: list[dict[str, object]] = []
    for hypothesis in outcome.hypotheses:
        items.append(
            {
                "source_class": "MOCK",
                "source_ref": outcome.playbook_version,
                "rule_version": "battery.playbook.v1",
                "content_summary": hypothesis.cause_summary,
                "confidence": hypothesis.confidence,
                "review_required": hypothesis.review_required,
            }
        )
    for missing in outcome.missing_items:
        items.append(
            {
                "source_class": "MISSING",
                "source_ref": "missing.items",
                "rule_version": "none",
                "content_summary": missing,
                "confidence": 0.0,
                "review_required": True,
            }
        )
    return items


@router.post("/diagnostics", status_code=status.HTTP_200_OK)
def run_diagnosis(
    payload: DiagnosisRequestPayload,
    subject: SubjectContext = Depends(current_subject),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    """售后故障诊断入口：输入症状+VIN/批次，输出六段归因结果。"""
    outcome = _service().run(
        DiagnosisRequest(
            question=payload.question,
            vin=payload.vin,
            claim_id=payload.claim_id,
            wo_id=payload.wo_id,
            batch_id=payload.batch_id,
        )
    )
    return {
        "request_id": idempotency_key or "local-request",
        "data": {
            "subject_id": subject.subject_id,
            "scenario": "after_sales",
            "domain": outcome.domain_code,
            "playbook_version": outcome.playbook_version,
            "question": payload.question,
            "key_metrics": {
                "hypothesis_count": len(outcome.hypotheses),
                "missing_count": len(outcome.missing_items),
            },
            "conclusion": outcome.conclusion,
            "missing_items": list(outcome.missing_items),
            "manual_review_required": outcome.manual_review_required,
            "evidence": _evidence_items(outcome),
        },
    }
