"""冒烟测试：报告升级（时间线/业务数据/向量数据渲染）。"""
from attribution_analysis.api.export_report import timeline_html, biz_data_html, vector_data_html


def _execs():
    return [
        {"step_no": 1, "tool_name": "query_business_data", "status": "success", "duration_ms": 1200,
         "details": {"backend": "http://127.0.0.1:8012", "sql": "SELECT * FROM orders", "columns": ["产品", "金额"],
                     "rows": [["电子产品", 38995], ["服装", 2098]], "row_count": 2}},
        {"step_no": 2, "tool_name": "query_knowledge_base", "status": "success", "duration_ms": 300,
         "details": {"backend": "demo.manual.delivery.v1", "query": "交付延迟", "hit_count": 1,
                     "hits": [{"title": "履约规则", "content": "承诺日期与签收日期差值判断延迟。", "source_ref": "demo.manual.delivery.v1", "score": 0.98, "source_class": "MOCK"}]}},
        {"step_no": 3, "tool_name": "synthesize_with_llm", "status": "success", "duration_ms": 5000,
         "details": {"model": "deepseek-v4-flash"}},
    ]


def test_timeline_renders_steps_and_status():
    html = timeline_html(_execs())
    assert "步骤 1" in html and "业务数据查询（NL2SQL）" in html
    assert "成功" in html and "1.2s" in html


def test_biz_data_renders_sql_and_table():
    html = biz_data_html(_execs())
    assert "SELECT * FROM orders" in html
    assert "电子产品" in html and "38995" in html
    assert "2 行" in html


def test_biz_data_renders_failure():
    exes = [{"step_no": 1, "tool_name": "query_business_data", "status": "failed",
             "details": {"backend": "x", "error_type": "TimeoutError", "error_message": "timed out"}}]
    html = biz_data_html(exes)
    assert "timed out" in html and "失败" in html


def test_vector_data_renders_hits_with_score():
    html = vector_data_html(_execs())
    assert "履约规则" in html and "98%" in html
    assert "demo.manual.delivery.v1" in html
