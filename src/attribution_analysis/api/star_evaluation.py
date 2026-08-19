"""S7 服务店星级评定 HTTP 接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.application.scenarios.star_evaluation import StarEvaluationRequest, StarEvaluationService
from attribution_analysis.infrastructure.composition import open_database_by_url

router = APIRouter(prefix="/api/v1/star-evaluation", tags=["star-evaluation"])


class StarEvaluationPayload(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    station_code: str | None = None


@router.post("/analyze", status_code=status.HTTP_200_OK)
def run_analysis(
    payload: StarEvaluationPayload,
    subject: SubjectContext = Depends(current_subject),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    """S7 服务店星级评定入口：按检查项一票否决 + 总分计算。"""
    service = StarEvaluationService(open_database_by_url())
    if not service.is_star_scenario(payload.question):
        raise HTTPException(status_code=400, detail="问题不属于星级评定场景")
    result = service.run(StarEvaluationRequest(question=payload.question, station_code=payload.station_code))
    return {"request_id": idempotency_key or "local-request", "data": {"subject_id": subject.subject_id, "scenario": result["scenario"], "question": payload.question, "conclusion": result["conclusion"], "key_metrics": result["key_metrics"], "missing_items": result["missing_items"], "manual_review_required": result["manual_review_required"], "evidence": result["evidence"]}}
