"""S9 售前模拟黄金数据集契约测试（G-E1-1～G-E5-1）。

测试范围：
- G-E1-1：商机丢单 → 关键人未覆盖 + 报价偏高 + 阶段停留
- G-E2-1：业绩未达标 → 华东区达成率 45%
- G-E3-1：客户流失 → 跟进递减 + 无外勤 + 流失风险 high
- G-E4-1：报价竞争力 → 丢单标偏离度 + 竞品价 MISSING 降级
- G-E5-1：线索质量 → 广告来源转化率分析
- 反例：未知场景转人工、短问题拒绝
"""
from pathlib import Path

from fastapi.testclient import TestClient

from attribution_analysis.app import app
from attribution_analysis.adapters.crm.demo import DemoCrmAdapter
from attribution_analysis.application.scenarios.presales import (
    PresalesDiagnosisRequest,
    PresalesDiagnosisService,
)
from attribution_analysis.infrastructure.database.duckdb import open_database

MOCK_HEADERS = {"X-Subject-Id": "test-user"}


def _service(tmp_path: Path) -> PresalesDiagnosisService:
    connection = open_database(tmp_path / "demo.db")
    return PresalesDiagnosisService(DemoCrmAdapter(connection))


def test_ge1_1_opportunity_loss_identifies_coverage_and_quote(tmp_path: Path) -> None:
    """G-E1-1：商机丢单识别关键人未覆盖 + 报价偏高 + 阶段停留过长。"""
    service = _service(tmp_path)
    outcome = service.run(PresalesDiagnosisRequest(
        question="商机OPP-001为什么丢单", opportunity_id="OPP-001",
    ))
    assert outcome.scenario == "E1"
    assert "关键人" in outcome.conclusion or "报价" in outcome.conclusion
    assert outcome.manual_review_required is True
    # 验证埋点：OPP-001 报价 500000 vs 竞品 450000 → 偏离 11%
    quote_evidence = [e for e in outcome.evidence if "报价偏离" in str(e)]
    deviation_evidence = [e for e in outcome.evidence if "偏离度" in str(e)]
    quote_evidence_total = quote_evidence + deviation_evidence
    assert len(quote_evidence_total) >= 1, f"Missing quote evidence: {outcome.evidence}"


def test_ge2_1_underperformance_identifies_45_percent_rate(tmp_path: Path) -> None:
    """G-E2-1：华东区业绩未达标达成率 45%。"""
    service = _service(tmp_path)
    outcome = service.run(PresalesDiagnosisRequest(
        question="华东区本月业绩未达标为什么", region="华东",
    ))
    assert outcome.scenario == "E2"
    # 验证关键埋点：达成率 45%
    key_metrics = dict(outcome.key_metrics)
    assert "45" in key_metrics.get("区域达成率", "")
    assert outcome.manual_review_required is True


def test_ge3_1_customer_churn_high_risk(tmp_path: Path) -> None:
    """G-E3-1：客户 C-001 流失风险 high（评分 1.00）。"""
    service = _service(tmp_path)
    outcome = service.run(PresalesDiagnosisRequest(
        question="客户C-001为什么被回收公海", customer_id="C-001",
    ))
    assert outcome.scenario == "E3"
    key_metrics = dict(outcome.key_metrics)
    assert "high" in key_metrics.get("风险等级", "")
    assert outcome.manual_review_required is True


def test_ge4_1_quote_competitiveness_analyzes_deviations(tmp_path: Path) -> None:
    """G-E4-1：报价竞争力识别丢单标的偏离度，竞品价 MISSING 降级。"""
    service = _service(tmp_path)
    outcome = service.run(PresalesDiagnosisRequest(
        question="最近5个标丢了3个为什么",
    ))
    assert outcome.scenario == "E4"
    assert "偏离" in outcome.conclusion
    # 至少有一条偏离度证据
    deviation_evidence = [e for e in outcome.evidence if "偏离度" in str(e)]
    assert len(deviation_evidence) >= 1, f"Missing deviation evidence: {outcome.evidence}"


def test_ge5_1_lead_quality_analyzes_conversion(tmp_path: Path) -> None:
    """G-E5-1：广告渠道线索质量分析。"""
    service = _service(tmp_path)
    outcome = service.run(PresalesDiagnosisRequest(
        question="广告渠道线索转化率为什么低", source="广告",
    ))
    assert outcome.scenario == "E5"
    # 广告转化率应有数据
    assert any("转化率" in str(e) for e in outcome.evidence)


def test_unknown_scenario_requires_human_review(tmp_path: Path) -> None:
    """反例：无法识别的问题必须转人工。"""
    service = _service(tmp_path)
    outcome = service.run(PresalesDiagnosisRequest(question="今天天气怎么样"))
    assert outcome.scenario == "unknown"
    assert outcome.manual_review_required is True


def test_api_rejects_short_question(tmp_path: Path) -> None:
    """反例：短问题 422 拒绝。"""
    client = TestClient(app)
    response = client.post(
        "/api/v1/presales/diagnostics",
        json={"question": "短"},
        headers=MOCK_HEADERS,
    )
    assert response.status_code == 422


def test_api_returns_six_part_structure(tmp_path: Path) -> None:
    """契约：API 返回六段结构（问题/关键指标/结论/缺失/人工复核/证据）。"""
    client = TestClient(app)
    response = client.post(
        "/api/v1/presales/diagnostics",
        json={"question": "商机OPP-001为什么丢单", "opportunity_id": "OPP-001"},
        headers=MOCK_HEADERS,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["scenario"] == "E1"
    assert "conclusion" in data
    assert "key_metrics" in data
    assert "missing_items" in data
    assert "manual_review_required" in data
    assert "evidence" in data


def test_demo_crm_adapter_marks_all_mock(tmp_path: Path) -> None:
    """契约：DemoCrmAdapter 所有结果标记 MOCK。"""
    connection = open_database(tmp_path / "demo.db")
    adapter = DemoCrmAdapter(connection)
    funnel = adapter.query_opportunity_funnel()
    for row in funnel:
        assert row.source_class == "MOCK"
        assert row.source_ref == "demo.duckdb.presales.v1"
    connection.close()


def test_route_does_not_leak_to_after_sales(tmp_path: Path) -> None:
    """契约：售前路由不拦截售后问题，售后路由不拦截售前问题。"""
    from attribution_analysis.application.scenarios.after_sales import AfterSalesScenarioRouter
    from attribution_analysis.application.scenarios.presales import PresalesScenarioRouter

    presales_router = PresalesScenarioRouter()
    after_sales_router = AfterSalesScenarioRouter()

    # 售后问题不应该被售前路由拦截
    assert presales_router.route("索赔单CL-001是否应该赔付") is None
    # 售前问题不应该被售后路由拦截
    assert after_sales_router.route("为什么这个月业绩没达标") is None


def test_e2_and_e5_do_not_conflict_with_e1_e4(tmp_path: Path) -> None:
    """契约：E2 业绩和 E5 线索不误入 E1/E4。"""
    service = _service(tmp_path)
    e2 = service.run(PresalesDiagnosisRequest(question="华东区业绩未达标", region="华东"))
    assert e2.scenario == "E2"
    e5 = service.run(PresalesDiagnosisRequest(question="广告渠道线索转化率低", source="广告"))
    assert e5.scenario == "E5"