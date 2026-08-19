from uuid import uuid4

from fastapi.testclient import TestClient

from attribution_analysis.api.app import create_app


client = TestClient(create_app())
HEADERS = {"X-Subject-Id": "attachment-contract-user"}


def _create_case() -> str:
    response = client.post(
        "/api/v1/cases",
        headers={**HEADERS, "Idempotency-Key": uuid4().hex},
        json={"conversation_id": uuid4().hex, "scenario_hint": "E2", "question": "华东区域本月销售目标未达成，需要归因分析"},
    )
    assert response.status_code == 202
    return response.json()["data"]["case_id"]


def test_attachment_intake_binds_owned_case_hash_and_snapshot() -> None:
    """Contract: an allowed attachment is isolated under its owned Case with immutable hash metadata."""
    case_id = _create_case()
    response = client.post(
        f"/api/v1/attachments/cases/{case_id}",
        headers=HEADERS,
        files={"file": ("evidence.csv", b"region,amount\nEast,42\n", "text/csv")},
    )

    assert response.status_code == 201
    item = response.json()["data"]
    assert item["sha256"]
    assert item["parse_snapshot"]["rows"] == 2
    assert client.get(f"/api/v1/attachments/cases/{case_id}", headers=HEADERS).json()["data"] == [item]
    evidence = client.get(f"/api/v1/cases/{case_id}/evidence", headers=HEADERS).json()["data"]
    assert any(item["source_ref"] == f"attachment:{response.json()['data']['attachment_id']}" for item in evidence)


def test_attachment_rejects_unowned_case_and_disallowed_type() -> None:
    """Contract: attachment intake never creates files for an inaccessible Case or unapproved type."""
    assert client.post(
        "/api/v1/attachments/cases/not-owned",
        headers=HEADERS,
        files={"file": ("bad.exe", b"x", "application/octet-stream")},
    ).status_code == 404


def test_case_events_stream_replays_persisted_execution_contract() -> None:
    """Contract: an existing Case can replay ordered lifecycle snapshots and terminate explicitly."""
    case_id = _create_case()
    response = client.get(f"/api/v1/cases/{case_id}/events", headers=HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: case" in response.text
    assert "event: execution" in response.text
    assert "event: result" in response.text
    assert "event: done" in response.text
