"""S8 供应商反向索赔 HTTP 接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.application.scenarios.supplier_recourse import SupplierRecourseRequest, SupplierRecourseService
from attribution_analysis.infrastructure.composition import open_database_by_url

router = APIRouter(prefix="/api/v1/supplier-recourse", tags=["supplier-recourse"])


class SupplierRecoursePayload(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    supplier_id: str | None = None
    claim_id: str | None = None
    batch_id: str | None = None


@router.post("/analyze", status_code=status.HTTP_200_OK)
def run_analysis(
    payload: SupplierRecoursePayload,
    subject: SubjectContext = Depends(current_subject),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    """S8 供应商反向索赔入口：评估合同在期 + 不良率 + 批次异常。"""
    service = SupplierRecourseService(open_database_by_url())
    if not service.is_supplier_scenario(payload.question):
        raise HTTPException(status_code=400, detail="问题不属于供应商追偿场景")
    result = service.run(SupplierRecourseRequest(question=payload.question, supplier_id=payload.supplier_id, claim_id=payload.claim_id, batch_id=payload.batch_id))
    return {"request_id": idempotency_key or "local-request", "data": {"subject_id": subject.subject_id, "scenario": result["scenario"], "question": payload.question, "conclusion": result["conclusion"], "key_metrics": result["key_metrics"], "missing_items": result["missing_items"], "manual_review_required": result["manual_review_required"], "evidence": result["evidence"]}}
