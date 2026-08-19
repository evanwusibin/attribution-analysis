"""S4 故障报修与维修诊断（电池包为首域）契约测试。"""
from pathlib import Path

from fastapi.testclient import TestClient

from attribution_analysis.adapters.after_sales.demo import DemoAfterSalesAdapter
from attribution_analysis.app import app
from attribution_analysis.application.scenarios.after_sales import DiagnosisRequest, FaultDiagnosisService
from attribution_analysis.infrastructure.database.duckdb import open_database


def _service(tmp_path: Path) -> FaultDiagnosisService:
    connection = open_database(tmp_path / "demo.db")
    return FaultDiagnosisService(DemoAfterSalesAdapter(connection))


def test_g_c_1_batch_anomaly_produces_candidate_not_verdict(tmp_path: Path) -> None:
    """Contract (G-C-1): a batch with 8% defect rate yields a candidate hypothesis plus missing list, never an action."""
    service = _service(tmp_path)
    outcome = service.run(DiagnosisRequest(question="批次B-2024-Q1电池包故障率异常，为什么", batch_id="B-2024-Q1"))

    assert outcome.domain_code == "battery_pack"
    assert any("8%" in h.cause_summary and "行业均值" in h.cause_summary for h in outcome.hypotheses)
    assert "采购质保合同与批次追溯（MISSING）" in outcome.missing_items
    assert outcome.manual_review_required is True
    assert all(h.review_required for h in outcome.hypotheses)


def test_soh_anomaly_requires_human_review_not_auto_denial(tmp_path: Path) -> None:
    """Contract (G-A-5): SOH=70% with MOCK threshold must request human review and never auto-rule."""
    service = _service(tmp_path)
    outcome = service.run(
        DiagnosisRequest(question="电池包SOC异常，SOH只有70%", vin="LSGAB52R7DF000005")
    )

    assert outcome.manual_review_required is True
    assert "检测方法与容量判定条款（FACT）" in outcome.missing_items
    assert "诊断报告（FACT）" in outcome.missing_items
    hypothesis = outcome.hypotheses[0]
    assert hypothesis.review_required is True
    assert "MOCK" in hypothesis.supporting_evidence[0] or "MOCK" in " ".join(hypothesis.supporting_evidence)


def test_negative_case_anomalous_value_never_triggers_disposition(tmp_path: Path) -> None:
    """Contract (反例): a low SOH can never be turned into an auto denial or recourse decision."""
    service = _service(tmp_path)
    outcome = service.run(
        DiagnosisRequest(question="电池包SOC异常，SOH只有70%", vin="LSGAB52R7DF000005")
    )

    assert "拒赔" not in outcome.conclusion
    assert "追偿" not in outcome.conclusion
    assert "自然衰减" not in outcome.conclusion
    assert outcome.manual_review_required is True


def test_normal_soh_does_not_force_review(tmp_path: Path) -> None:
    """Contract: a healthy SOH (92%) does not force human review by itself."""
    service = _service(tmp_path)
    outcome = service.run(
        DiagnosisRequest(question="电池包SOC异常", vin="LSGAB52R7DF000001")
    )

    assert outcome.manual_review_required is False
    assert outcome.hypotheses[0].review_required is False


def test_unknown_domain_routes_to_human(tmp_path: Path) -> None:
    """Contract: unresolvable symptoms cannot fabricate a domain conclusion."""
    service = _service(tmp_path)
    outcome = service.run(DiagnosisRequest(question="发动机异响无法启动"))

    assert outcome.domain_code == "unknown"
    assert outcome.manual_review_required is True
    assert not outcome.hypotheses


def test_scenario_router_distinguishes_after_sales(tmp_path: Path) -> None:
    """Contract: after-sales keywords route to the after-sales scenario; sales questions do not."""
    service = _service(tmp_path)

    assert service.is_after_sales("为什么索赔单被退回") is True
    assert service.is_after_sales("电池包SOC异常") is True
    assert service.is_after_sales("为什么这个月业绩没达标") is False


def test_diagnostics_api_returns_six_part_structure(tmp_path: Path) -> None:
    """Contract: the API exposes question/metrics/conclusion/missing/review/evidence."""
    connection = open_database(tmp_path / "demo.db")
    client = TestClient(app)

    response = client.post(
        "/api/v1/after-sales/diagnostics",
        json={"question": "电池包SOC异常，SOH只有70%", "vin": "LSGAB52R7DF000005"},
        headers={"X-Subject-Id": "test-user"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["scenario"] == "after_sales"
    assert data["domain"] == "battery_pack"
    assert data["manual_review_required"] is True
    assert data["key_metrics"]["hypothesis_count"] >= 1
    assert any(item["source_class"] == "MISSING" for item in data["evidence"])
    assert any(item["source_class"] == "MOCK" for item in data["evidence"])
    connection.close()


def test_diagnostics_api_rejects_short_question(tmp_path: Path) -> None:
    """Contract: invalid input is rejected before any diagnosis runs."""
    client = TestClient(app)
    response = client.post(
        "/api/v1/after-sales/diagnostics",
        json={"question": "短"},
        headers={"X-Subject-Id": "test-user"},
    )

    assert response.status_code == 422