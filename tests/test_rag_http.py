import json

import pytest

from attribution_analysis.adapters.rag import http as http_adapter
from attribution_analysis.adapters.rag.http import HttpRAGAdapter


class _Response:
    def __init__(self, body: str) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.body.encode("utf-8")


def test_query_only_promotes_real_answer_to_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response('{"message":"流程已完成","session_id":"s1"}')

    monkeypatch.setattr(http_adapter, "urlopen", fake_urlopen)
    assert HttpRAGAdapter("http://rag", 9).retrieve("查规则") == ()
    assert captured["body"] == {"query": "查规则", "session_id": "attribution-analysis", "is_stream": False}


def test_import_uploads_each_file_for_single_file_service_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[tuple[str, bytes]] = []
    responses = iter((_Response('{"task_ids":["t1"]}'), _Response('{"task_ids":["t2"]}')))

    def fake_urlopen(request, timeout):
        requests.append((request.full_url, request.data))
        return next(responses)

    monkeypatch.setattr(http_adapter, "urlopen", fake_urlopen)
    tasks = HttpRAGAdapter("http://rag", import_base_url="http://import").import_documents(
        (("a.txt", "text/plain", b"A"), ("b.txt", "text/plain", b"B"))
    )

    assert [task.task_id for task in tasks] == ["t1", "t2"]
    assert [url for url, _ in requests] == ["http://import/upload", "http://import/upload"]
    assert b'filename="a.txt"' in requests[0][1]
    assert b'filename="b.txt"' in requests[1][1]
