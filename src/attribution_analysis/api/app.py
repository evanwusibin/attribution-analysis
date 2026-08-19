"""HTTP 应用工厂。

路由只在这里组装；业务用例和外部适配器不得被 HTTP 层直接创建。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from attribution_analysis.api.after_sales import router as after_sales_router
from attribution_analysis.api.auth import router as auth_router
from attribution_analysis.api.cases import router as cases_router
from attribution_analysis.api.claim_compliance import router as claim_compliance_router
from attribution_analysis.api.complaint_analysis import router as complaint_analysis_router
from attribution_analysis.api.constants import SERVICE_VERSION
from attribution_analysis.api.export_report import router as export_router
from attribution_analysis.api.health import router as health_router
from attribution_analysis.api.presales import router as presales_router
from attribution_analysis.api.star_evaluation import router as star_evaluation_router
from attribution_analysis.api.supplier_recourse import router as supplier_recourse_router
from attribution_analysis.api.attachments import router as attachments_router
from attribution_analysis.api.knowledge import router as knowledge_router
from attribution_analysis.config.settings import settings, validate_production_settings


def create_app() -> FastAPI:
    """创建独立的 HTTP 应用边界。"""
    blockers = validate_production_settings(settings)
    if blockers:
        raise RuntimeError(f"production startup blocked: {'; '.join(blockers)}")
    application = FastAPI(
        title="Attribution Analysis",
        version=SERVICE_VERSION,
        description="Evidence-governed business attribution analysis.",
    )
    if settings.environment in {"local", "test", "docker"}:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "Idempotency-Key", "X-Subject-Id", "Authorization"],
        )
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(cases_router)
    application.include_router(after_sales_router)
    application.include_router(presales_router)
    application.include_router(claim_compliance_router)
    application.include_router(complaint_analysis_router)
    application.include_router(star_evaluation_router)
    application.include_router(supplier_recourse_router)
    application.include_router(export_router)
    application.include_router(attachments_router)
    application.include_router(knowledge_router)
    frontend_directory = Path(__file__).resolve().parents[3] / "frontend"

    @application.get("/", include_in_schema=False)
    def redirect_to_workbench() -> RedirectResponse:
        """根路径重定向到前端工作台。"""
        return RedirectResponse(url="/workbench/")

    # 前端由独立容器/静态服务提供；本地开发存在 frontend 目录时才挂载工作台。
    if frontend_directory.is_dir():
        application.mount("/workbench", StaticFiles(directory=frontend_directory, html=True), name="workbench")
    return application
