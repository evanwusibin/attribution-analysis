"""索赔合规 API 路由（S5）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.application.scenarios.claim_compliance import (
    ClaimComplianceService,
    ClaimComplianceRequest,
)
from attribution_analysis.adapters.warranty.demo import DemoWarrantyAdapter

router = APIRouter(prefix="/api/claim-compliance", tags=["claim-compliance"])


class ClaimComplianceRequestModel(BaseModel):
    """索赔合规请求模型。"""

    question: str = Field(..., min_length=5, description="问题描述")
    claim_id: str | None = Field(None, description="索赔单号")
    action: str = Field("evaluate", description="动作：evaluate | reauthorize")


@router.post("/analyze")
def analyze_claim_compliance(
    request: ClaimComplianceRequestModel,
    subject: SubjectContext = Depends(current_subject),
) -> dict:
    """分析索赔合规性。

    - action=evaluate: 评估索赔资格（G-A-1～G-A-6）
    - action=reauthorize: 评估重新授权资格（G-A-7）
    """
    warranty_adapter = DemoWarrantyAdapter()
    service = ClaimComplianceService(warranty_adapter)

    if not service.is_claim_compliance(request.question):
        raise HTTPException(
            status_code=400,
            detail="问题不属于索赔合规场景",
        )

    req = ClaimComplianceRequest(
        question=request.question,
        claim_id=request.claim_id,
        action=request.action,
    )

    result = service.run(req)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@router.get("/claim/{claim_id}")
def get_claim_info(
    claim_id: str,
    subject: SubjectContext = Depends(current_subject),
) -> dict:
    """查询索赔单基本信息。"""
    adapter = DemoWarrantyAdapter()
    claim = adapter.get_claim(claim_id)
    
    if not claim:
        raise HTTPException(status_code=404, detail="索赔单不存在")
    
    vehicle = adapter.get_vehicle(claim.vin)
    
    return {
        "claim": {
            "claim_id": claim.claim_id,
            "wo_id": claim.wo_id,
            "vin": claim.vin,
            "fault_desc": claim.fault_desc,
            "parts_list": claim.parts_list,
            "claim_amount": claim.claim_amount,
            "claim_status": claim.claim_status,
            "total_mileage": claim.total_mileage,
            "created_at": claim.created_at,
        },
        "vehicle": {
            "vin": vehicle.vin if vehicle else None,
            "vehicle_model": vehicle.vehicle_model if vehicle else None,
            "delivery_date": vehicle.delivery_date if vehicle else None,
        } if vehicle else None,
    }
