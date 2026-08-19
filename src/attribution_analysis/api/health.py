"""系统级 HTTP 路由。

Slice 0 只提供服务就绪检查，不创建归因任务或返回业务结论。
"""

from fastapi import APIRouter

from attribution_analysis.api.constants import SERVICE_NAME


router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """返回稳定的本地服务就绪载荷。"""
    return {"status": "ok", "service": SERVICE_NAME}
