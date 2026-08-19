"""S6 重复维修与客户投诉归因 HTTP 接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.application.scenarios.complaint_analysis import ComplaintAnalysisRequest, ComplaintAnalysisService
from attribution_analysis.infrastructure.composition import open_database_by_url

router = APIRouter(prefix="/api/v1/complaint-analysis", tags=["complaint-analysis"])


class ComplaintAnalysisPayload(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    vin: str | None = None
    complaint_id: str | None = None
    wo_id: str | None = None


@router.post("/diagnostics", status_code=status.HTTP_200_OK)
def run_diagnostics(
    payload: ComplaintAnalysisPayload,
    subject: SubjectContext = Depends(current_subject),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    """S6 投诉/重复维修归因入口：识别重复维修模式与投诉根因。"""
    service = ComplaintAnalysisService(open_database_by_url())
    if not service.is_complaint_scenario(payload.question):
        raise HTTPException(status_code=400, detail="问题不属于投诉/重复维修场景")
    result = service.run(ComplaintAnalysisRequest(
        question=payload.question, vin=payload.vin, complaint_id=payload.complaint_id, wo_id=payload.wo_id,
    ))
    return {"request_id": idempotency_key or "local-request", "data": {"subject_id": subject.subject_id, "scenario": result["scenario"], "question": payload.question, "conclusion": result["conclusion"], "key_metrics": result["key_metrics"], "missing_items": result["missing_items"], "manual_review_required": result["manual_review_required"], "evidence": result["evidence"]}}
