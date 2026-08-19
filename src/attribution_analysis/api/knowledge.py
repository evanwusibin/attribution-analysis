"""掌柜智库独立知识库边界：检索与导入直接转发到真实 RAG 服务。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.api.cases import service
from attribution_analysis.ports.evidence import KnowledgeImportPort

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])
MAX_IMPORT_SIZE = 50 * 1024 * 1024


def _backend() -> KnowledgeImportPort:
    """返回已由组合根装配的导入能力；演示适配器不会伪装成可管理知识库。"""
    backend = service.evidence_toolset.rag
    if not hasattr(backend, "import_documents"):
        raise HTTPException(status_code=503, detail="独立知识库导入服务未配置")
    return backend  # type: ignore[return-value]


@router.get("/query")
def query_knowledge(query: str = Query(min_length=2, max_length=2000), subject: SubjectContext = Depends(current_subject)) -> dict[str, object]:
    """独立调用掌柜智库检索；结果保留服务级定位，不伪造原始分块。"""
    del subject
    try:
        hits = service.evidence_toolset.rag.retrieve(query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"掌柜智库检索服务不可用：{type(exc).__name__}") from exc
    return {"data": [{"title": hit.title, "content": hit.content, "source_ref": hit.source_ref, "score": hit.score, "source_class": hit.source_class} for hit in hits]}


async def import_documents(
    files: list[UploadFile] = File(...),
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """将文件提交给掌柜智库的 /upload，不复制或改写其导入流程。"""
    del subject
    if not files:
        raise HTTPException(status_code=422, detail="至少选择一个文件")
    payload: list[tuple[str, str, bytes]] = []
    for file in files:
        content = await file.read(MAX_IMPORT_SIZE + 1)
        if len(content) > MAX_IMPORT_SIZE:
            raise HTTPException(status_code=413, detail="单个知识库文件不得超过 50MB")
        payload.append((file.filename or "unnamed", file.content_type or "application/octet-stream", content))
    try:
        tasks = _backend().import_documents(tuple(payload))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"掌柜智库导入服务不可用：{type(exc).__name__}") from exc
    return {"data": [{"task_id": task.task_id, "status": task.status} for task in tasks]}


@router.get("/import/{task_id}")
def import_status(task_id: str, subject: SubjectContext = Depends(current_subject)) -> dict[str, object]:
    """读取掌柜智库原生导入任务状态。"""
    del subject
    try:
        task = _backend().import_status(task_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"掌柜智库状态服务不可用：{type(exc).__name__}") from exc
    return {"data": {"task_id": task.task_id, "status": task.status, "done_list": list(task.done_list), "running_list": list(task.running_list)}}
