"""RAG HTTP 适配器：复用掌柜智库已运行的知识库服务。"""
from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from attribution_analysis.ports.evidence import KnowledgeImportTask, RAGPort, RetrievalHit


class HttpRAGAdapter(RAGPort):
    """对齐掌柜智库的查询、导入和任务状态接口。"""

    def __init__(self, base_url: str, timeout_seconds: float = 30, import_base_url: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.import_base_url = (import_base_url or base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def retrieve(self, query: str, limit: int = 5) -> tuple[RetrievalHit, ...]:
        """调用真实同步查询；没有答案时不把流程提示伪装成知识命中。"""
        del limit
        payload = json.dumps({"query": query, "session_id": "attribution-analysis", "is_stream": False}).encode("utf-8")
        request = Request(f"{self.base_url}/query", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        answer = body.get("answer")
        if not answer:
            return ()
        return (RetrievalHit("掌柜智库 RAG 服务回答", str(answer), f"{self.base_url}/query", 1.0, "FACT"),)

    def import_documents(self, files: tuple[tuple[str, str, bytes], ...]) -> tuple[KnowledgeImportTask, ...]:
        """逐文件调用掌柜智库 /upload，兼容其当前只消费 files[0] 的实现。"""
        tasks: list[KnowledgeImportTask] = []
        for filename, content_type, content in files:
            boundary = "----AttributionKnowledgeBoundary"
            body = b"".join((
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{filename}\"\r\nContent-Type: {content_type or 'application/octet-stream'}\r\n\r\n".encode(),
                content,
                f"\r\n--{boundary}--\r\n".encode(),
            ))
            request = Request(
                f"{self.import_base_url}/upload",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
            tasks.extend(KnowledgeImportTask(str(task_id), "queued") for task_id in result.get("task_ids", ()))
        return tuple(tasks)

    def import_status(self, task_id: str) -> KnowledgeImportTask:
        """读取掌柜智库导入任务状态。"""
        request = Request(f"{self.import_base_url}/status/{quote(task_id, safe='')}", method="GET")
        with urlopen(request, timeout=self.timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        return KnowledgeImportTask(
            str(body.get("task_id", task_id)),
            str(body.get("status", "unknown")),
            tuple(body.get("done_list", ())),
            tuple(body.get("running_list", ())),
        )
