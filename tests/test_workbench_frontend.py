from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND = PROJECT_ROOT / "frontend"


def test_workbench_navigation_declares_real_view_boundaries() -> None:
    """Contract: every visible navigation target maps to an explicit, inspectable workbench view."""
    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    for view in ("workbench", "cases", "history", "evidence", "trace", "knowledge", "export"):
        assert f'data-view="{view}"' in markup
    for panel in ("casesView", "historyView", "evidenceView", "traceView", "knowledgeView", "exportView"):
        assert f'id="{panel}"' in markup
    assert "activeView:'workbench'" in script
    assert "scenario:'auto'" in script
    assert "state.scenario==='auto'?{}:{scenario_hint:state.scenario}" in script
    assert "正在建立 Case 与受控分析计划" in script
    assert "正在并行执行 RAG 资料召回与 NL2SQL 只读查询" in script
    assert "attachmentPanel" in script
    assert "已完成入库" in script
    assert "event{display:grid" in markup
    assert "文件清单和 Evidence 已写入当前 Case" in script
    assert "function setActiveView(view" in script
    assert "function renderNavigation()" in script


def test_welcome_catalog_and_composer_contracts() -> None:
    """Contract: all declared capabilities are visible, while upload remains one资料入口。"""
    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")
    for capability in (
        "E1 · 商机丢单", "E2 · 业绩归因", "E3 · 客户价值", "E4 · 区域经营", "E5 · 转化诊断",
        "S1 · 故障诊断", "S2 · 索赔合规", "S3 · 维修质量", "S4 · 配件异常", "S5 · 索赔风控",
        "S6 · 投诉归因", "S7 · 服务店评定", "S8 · 供应商追责",
    ):
        assert markup.count(capability) >= 1
    assert markup.count('id="attachmentInput"') == 1
    assert markup.count('id="attachmentButton"') == 1
    assert "border-top:0" in markup
    assert "border-radius:999px" in markup


def test_backend_auto_matching_has_safe_fallback() -> None:
    """Contract: automatic matching only selects known projections; unknown topics stay generic."""
    from attribution_analysis.application.core import infer_scenario

    assert infer_scenario("本月华东销售业绩为什么没有达成") == "E2"
    assert infer_scenario("某车辆报码无法启动") == "S1"
    assert infer_scenario("客户价值分层") is None


def test_login_background_uses_content_page_style() -> None:
    """Contract: login branding uses the content-page blue canvas without the legacy image."""
    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "radial-gradient(circle at 18% 18%" in markup
    assert "url('assets/login-bg.png')" not in markup


def test_knowledge_boundary_and_controlled_case_report_are_explicit() -> None:
    """Contract: knowledge limits remain visible and export is only available through a Case-owned report path."""
    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "knowledgeSearchForm" in markup
    assert "knowledgeImportButton" in markup
    assert "/knowledge/query" in script
    assert "/api/v1/knowledge/import" in script
    assert 'id="previewReportButton"' in markup
    assert 'id="downloadReportButton"' in markup
    assert "loadCaseReport" in script


def test_scenario_projection_execution_exposes_projection_details() -> None:
    """Contract: scenario projection ToolExecution payload must carry conclusion, metrics, missing items and evidence."""
    from attribution_analysis.application.core import (
        CreateCaseCommand,
        ScenarioProjection,
        ToolExecution,
        execution_payload,
    )
    from attribution_analysis.application.scenarios.workbench import ScenarioEvidence
    from attribution_analysis.domain.core import ExecutionStatus
    from attribution_analysis.domain.core import new_id, utc_now

    projection = ScenarioProjection(
        conclusion="候选假设：电池包 SOC 衰减。",
        key_metrics=({"name": "候选假设", "value": "2", "unit": "项", "period": "当前诊断"},),
        missing_items=("缺少电池健康度台账",),
        evidence=(ScenarioEvidence("MOCK", "battery.playbook.v1", "battery.playbook.v1", "SOC 衰减假设"),),
        manual_review_required=True,
    )
    execution = ToolExecution(
        execution_id=new_id("exec"),
        case_id="case_probe",
        plan_id="plan_probe",
        step_no=3,
        tool_name="scenario_projection",
        status=ExecutionStatus.SUCCEEDED,
        input_fingerprint="fp",
        started_at=utc_now(),
        finished_at=utc_now(),
        details={
            "scenario": "S1",
            "conclusion": projection.conclusion,
            "key_metrics": list(projection.key_metrics),
            "missing_items": list(projection.missing_items),
            "evidence": [
                {
                    "source_class": item.source_class,
                    "source_ref": item.source_ref,
                    "rule_version": item.rule_version,
                    "content_summary": item.content_summary,
                }
                for item in projection.evidence
            ],
            "manual_review_required": projection.manual_review_required,
        },
    )
    payload = execution_payload(execution, ())
    assert payload["tool_name"] == "scenario_projection"
    assert payload["details"]["conclusion"] == "候选假设：电池包 SOC 衰减。"
    assert payload["details"]["key_metrics"][0]["name"] == "候选假设"
    assert payload["details"]["missing_items"] == ["缺少电池健康度台账"]
    assert payload["details"]["evidence"][0]["content_summary"] == "SOC 衰减假设"


def test_frontend_renders_scenario_projection_details_in_modal() -> None:
    """Contract: the execution detail modal must render scenario projection content instead of a bare id fallback."""
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "scenario_projection" in script
    assert "场景投影结论" in script
    assert "details.conclusion" in script
    assert "details.missing_items" in script


def test_frontend_recovers_from_stale_case_404() -> None:
    """Contract: a 404 sync failure must clear the stale case and offer guidance instead of looping errors."""
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "case not found" in script or "not found" in script
    assert "该分析会话不存在或已过期" in script
    assert "请新建分析会话" in script
    assert "state.caseId=null" in script


def test_frontend_history_list_loads_conversation_cases_and_navigates() -> None:
    """Contract: the history view must call the conversation cases endpoint and make rows clickable."""
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "/conversations/" in script
    assert "loadHistory" in script
    assert "openHistoryCase" in script
    assert "data-open-case" in script
    assert "historyCases" in script


def test_frontend_flow_marks_current_node_and_steps_in() -> None:
    """Contract: the flow diagram must mark the current node and animate completed steps into view."""
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")
    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "currentIndex" in script
    assert "' current'" in script or "current'" in script
    assert "process-step.current" in markup
    assert "@keyframes step-in" in markup


def test_summary_drawer_close_has_one_inaccessible_state_contract() -> None:
    """Contract: X and Escape use the same close state and hidden drawer cannot receive clicks."""
    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert 'id="closeSummaryButton"' in markup
    assert ".summary-drawer[aria-hidden=\"true\"]" in markup
    assert "transform:translateX(100%)" in markup
    assert "pointer-events:none" in markup
    assert "drawer.inert=true" in script
    assert "drawer.inert=false" in script
    assert "state.returnFocus=null" in script
    assert "$('closeSummaryButton').addEventListener('click',()=>setDrawer(false))" in script


def test_home_and_login_visual_contracts_use_blue_intelligence_theme() -> None:
    """Contract: the welcome headline and login copy visibly use the blue gradient theme without the legacy image."""
    markup = (FRONTEND / "index.html").read_text(encoding="utf-8")

    assert "先界定问题，再形成可审计的归因判断" in markup
    assert "linear-gradient(100deg,#1261d8 0%,#2aa8ff 48%,#7c6cff 100%)" in markup
    assert "linear-gradient(100deg,#e4f7ff 0%,#8bdcff 48%,#b9b1ff 100%)" in markup
    assert "url('assets/login-bg.png')" not in markup


def test_knowledge_import_uses_real_task_status_contract() -> None:
    """Contract: an accepted knowledge import must expose task status, not only a client-side success message."""
    script = (FRONTEND / "app.js").read_text(encoding="utf-8")

    assert "pollKnowledgeTasks" in script
    assert "/knowledge/import/${encodeURIComponent(task.task_id)}" in script
    assert "已提交" in script
