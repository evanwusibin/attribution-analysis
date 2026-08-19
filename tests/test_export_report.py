from uuid import uuid4

from fastapi.testclient import TestClient

from attribution_analysis.api.app import create_app


client = TestClient(create_app())


def test_case_report_is_derived_from_owned_result_and_supports_two_templates() -> None:
    """Contract: a completed Case can produce either controlled HTML report template."""
    headers = {"X-Subject-Id": "report-contract-user", "Idempotency-Key": uuid4().hex}
    created = client.post(
        "/api/v1/cases",
        headers=headers,
        json={"conversation_id": uuid4().hex, "scenario_hint": "E2", "question": "华东区域本月销售目标未达成，需要归因分析"},
    )
    case_id = created.json()["data"]["case_id"]
    for style in ("mckinsey", "deloitte"):
        response = client.get(f"/api/v1/export/cases/{case_id}/report?style={style}", headers={"X-Subject-Id": headers["X-Subject-Id"]})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert f"case_{case_id}_{style}.html" in response.headers["content-disposition"]
        assert ("McKinsey" if style == "mckinsey" else "Deloitte") in response.text


def test_case_report_rejects_invalid_template() -> None:
    """Contract: report style is a closed set and cannot select arbitrary templates."""
    response = client.get(
        "/api/v1/export/cases/not-owned/report?style=arbitrary",
        headers={"X-Subject-Id": "report-contract-user"},
    )
    assert response.status_code == 422
