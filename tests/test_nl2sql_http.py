import json

import pytest

from attribution_analysis.adapters.nl2sql import http as http_adapter
from attribution_analysis.adapters.nl2sql.http import HttpNL2SQLAdapter


class _Response:
    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def __iter__(self):
        # 适配器现按字节行增量读取 SSE 流（收到 result 立即返回，避免读到 EOF 挂死）
        return iter(self.body.encode("utf-8").splitlines(keepends=True))


def test_http_nl2sql_matches_data_agent_sse_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response('data: {"type":"progress","step":"执行SQL","status":"success"}\n\ndata: {"type":"result","data":[{"orders":2}]}\n\n')

    monkeypatch.setattr(http_adapter, "urlopen", fake_urlopen)
    result = HttpNL2SQLAdapter("http://127.0.0.1:8000", 7).query("统计订单数")

    assert captured == {
        "url": "http://127.0.0.1:8000/api/v1/query",
        "body": {"question": "统计订单数"},
        "timeout": 7,
    }
    assert result.columns == ("orders",)
    assert result.rows == ({"orders": 2},)
    assert result.source_ref == "http://127.0.0.1:8000/api/v1/query"


def test_http_nl2sql_exposes_remote_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        http_adapter,
        "urlopen",
        lambda request, timeout: _Response('data: {"error":"backend unavailable"}\n\n'),
    )

    with pytest.raises(RuntimeError, match="backend unavailable"):
        HttpNL2SQLAdapter("http://127.0.0.1:8000").query("统计订单数")
