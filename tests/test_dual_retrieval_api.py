from uuid import uuid4

from fastapi.testclient import TestClient

from attribution_analysis.app import app


client = TestClient(app)


def test_case_executes_independent_business_and_knowledge_retrievals() -> None:
    """Contract: every MVP case records one controlled SQL evidence and one RAG evidence."""
    response = client.post(
        "/api/v1/cases",
        json={"conversation_id": uuid4().hex, "question": "分析订单交付延迟和库存风险"},
        headers={"Idempotency-Key": uuid4().hex, "X-Subject-Id": "dual-retrieval-user"},
    )

    assert response.status_code == 202
    case_id = response.json()["data"]["case_id"]
    evidence_response = client.get(
        f"/api/v1/cases/{case_id}/evidence",
        headers={"X-Subject-Id": "dual-retrieval-user"},
    )
    result_response = client.get(
        f"/api/v1/cases/{case_id}/results",
        headers={"X-Subject-Id": "dual-retrieval-user"},
    )

    evidence = evidence_response.json()["data"]
    assert [item["source_ref"] for item in evidence] == [
        "demo.duckdb.business.v1",
        "demo.manual.delivery.v1",
    ]
    assert all(item["source_class"] == "MOCK" for item in evidence)
    assert result_response.json()["data"][0]["evidence_ids"] == [item["evidence_id"] for item in evidence]
    assert result_response.json()["data"][0]["manual_review_required"] is True
