"""NL2SQL HTTP 适配器：调用旧问数服务的 SSE 查询接口。"""
from __future__ import annotations

import json
import time
from urllib.request import Request, urlopen

from attribution_analysis.ports.evidence import NL2SQLPort, QueryResult


_QUERY_PATH = "/api/v1/query"


class HttpNL2SQLAdapter(NL2SQLPort):
    """调用 data-agent 的 POST /api/v1/query 流式接口。"""

    def __init__(self, base_url: str, timeout_seconds: float = 60) -> None:
        """绑定旧问数服务地址与超时。"""
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def query(self, question: str) -> QueryResult:
        """发送 data-agent 请求，增量解析 type=result 的 SSE 事件。

        关键修复：旧实现用 ``response.read()`` 一次性读到流结束（EOF），但 data-agent
        在异常时不会关闭 SSE 连接、且会持续发送 progress 字节，导致 urllib 的 socket
        超时因“每收到一个字节就重置计时”而永久失效，整条分析卡死在 queued。现改为
        逐行增量读取 + 绝对截止时间：收到 result 立即返回，收到 error 或超时则抛异常，
        由上层（EvidenceToolset.collect）降级为 MISSING 证据，保证闭环必然收敛。
        """
        payload = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
        source_ref = f"{self.base_url}{_QUERY_PATH}"
        request = Request(
            source_ref,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
            method="POST",
        )
        deadline = time.monotonic() + self.timeout_seconds
        # 逐次读取超时：必须大于 data-agent 内部 LLM 调用（关键词扩充等）造成的
        # 静默期（实测 20-120s 内不发任何 SSE 事件），否则会在节点执行中途误判为挂起。
        # 总耗时仍由上方绝对截止时间约束。
        per_read = min(self.timeout_seconds, 190.0)
        with urlopen(request, timeout=per_read) as response:
            for raw_line in response:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        f"NL2SQL query exceeded integration timeout ({self.timeout_seconds}s)"
                    )
                line = raw_line.decode("utf-8", "replace")
                if not line.startswith("data:"):
                    continue
                data_field = line.removeprefix("data:").strip()
                if not data_field:
                    continue
                try:
                    event = json.loads(data_field)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "result":
                    result = event.get("data")
                    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
                        raise RuntimeError("NL2SQL result must be a list of row objects")
                    columns = tuple(result[0].keys()) if result else ()
                    return QueryResult(columns, tuple(result), "remote", source_ref, "FACT")
                if event.get("error") or event.get("status") == "error":
                    error = event.get("error") or event.get("message") or event.get("step")
                    raise RuntimeError(f"NL2SQL returned an error: {error}")
        raise RuntimeError("NL2SQL response stream ended without a result event")
