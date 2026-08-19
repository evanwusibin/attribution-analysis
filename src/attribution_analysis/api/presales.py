"""售前诊断 HTTP 接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, Field

from attribution_analysis.adapters.crm.demo import DemoCrmAdapter
from attribution_analysis.adapters.crm.mysql import MysqlCrmAdapter
from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.application.scenarios.presales import PresalesDiagnosisRequest, PresalesDiagnosisService
from attribution_analysis.config.settings import settings
from attribution_analysis.infrastructure.composition import open_database_by_url, open_demo_database

router = APIRouter(prefix="/api/v1/presales", tags=["presales"])


class PresalesDiagnosisPayload(BaseModel):
    question: str = Field(min_length=5, max_length=2000)
    customer_id: str | None = None
    opportunity_id: str | None = None
    sales_person_id: str | None = None
    region: str | None = None
    source: str | None = None


def _service() -> PresalesDiagnosisService:
    """按数据库 URL 装配售前诊断服务：MySQL 用真实适配器，DuckDB 用 Demo 适配器。"""
    if settings.database_url.startswith("mysql://"):
        return PresalesDiagnosisService(MysqlCrmAdapter(open_database_by_url(settings.database_url)))
    return PresalesDiagnosisService(DemoCrmAdapter(open_demo_database()))


@router.post("/diagnostics", status_code=status.HTTP_200_OK)
def run_diagnosis(
    payload: PresalesDiagnosisPayload,
    subject: SubjectContext = Depends(current_subject),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, object]:
    """售前场景诊断入口：路由到 E1-E5 任一场景并返回六段结果。"""
    outcome = _service().run(PresalesDiagnosisRequest(
        question=payload.question, customer_id=payload.customer_id, opportunity_id=payload.opportunity_id,
        sales_person_id=payload.sales_person_id, region=payload.region, source=payload.source,
    ))
    return {"request_id": idempotency_key or "local-request", "data": {"subject_id": subject.subject_id, "scenario": outcome.scenario, "question": payload.question, "key_metrics": dict(outcome.key_metrics), "conclusion": outcome.conclusion, "missing_items": list(outcome.missing_items), "manual_review_required": outcome.manual_review_required, "evidence": [dict(item) for item in outcome.evidence]}}
