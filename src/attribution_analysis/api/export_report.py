"""报告导出 HTTP 接口。

支持 HTML 和 PDF 两种格式。
- HTML: 直接渲染 Jinja2 模板返回
- PDF: 通过 Playwright 截图 HTML 转 PDF（需要浏览器环境）

两种风格：
- mckinsey: 简洁数据驱动，MECE 结构
- deloitte: 详细图表丰富，红绿灯标识
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from fastapi.responses import HTMLResponse
from html import escape

from attribution_analysis.api.authentication import SubjectContext, current_subject
from attribution_analysis.api.cases import service
from attribution_analysis.application.core import CaseNotFoundError, evidence_payload, execution_payload, result_payload

router = APIRouter(prefix="/api/v1/export", tags=["export"])
report_audit: list[dict[str, str]] = []


def md_to_html(text: str) -> str:
    """将 LLM 的 Markdown 结论安全渲染为 HTML（先转义，再应用受控语法）。"""
    if not text:
        return "<p>（未生成结论）</p>"
    s = escape(str(text))
    lines = s.split("\n")
    out: list[str] = []
    in_ul = in_ol = False
    table: list[str] = []

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>"); in_ul = False
        if in_ol:
            out.append("</ol>"); in_ol = False

    def flush_table() -> None:
        nonlocal table
        if not table:
            return
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table]
        header = rows[0]
        body = rows[1:]
        if body and all(re.match(r"^:?-{2,}:?$", c) for c in body[0]):
            body = body[1:]
        h = '<table class="md-table"><thead><tr>' + "".join(f"<th>{c}</th>" for c in header) + "</tr></thead><tbody>"
        h += "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in body) + "</tbody></table>"
        out.append(h); table = []

    for raw in lines:
        line = raw.rstrip()
        if re.match(r"^\s*\|.*\|\s*$", line):
            close_lists(); table.append(line); continue
        if table and not line.startswith("|"):
            flush_table()
        if line.strip() == "":
            close_lists(); continue
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            close_lists(); out.append(f'<h{len(m.group(1))}>{m.group(2)}</h{len(m.group(1))}>'); continue
        if re.match(r"^\s*[-*]\s+", line):
            if not in_ul:
                close_lists(); out.append("<ul>"); in_ul = True
            out.append(f"<li>{re.sub(r'^\s*[-*]\s+', '', line)}</li>"); continue
        if re.match(r"^\s*\d+\.\s+", line):
            if not in_ol:
                close_lists(); out.append("<ol>"); in_ol = True
            out.append(f"<li>{re.sub(r'^\s*\d+\.\s+', '', line)}</li>"); continue
        if line.startswith("&gt;"):
            close_lists(); out.append(f"<blockquote>{line[4:].strip()}</blockquote>"); continue
        if line.strip() in {"---", "***"}:
            close_lists(); out.append("<hr>"); continue
        close_lists(); out.append(f"<p>{line}</p>")
    flush_table(); close_lists()
    body = "\n".join(out)
    body = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", body)
    body = re.sub(r"`([^`]+)`", r"<code>\1</code>", body)
    body = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", body)
    return body


def swot_html(conclusion: str, missing_items: list[str]) -> str:
    """从结论中提取 SWOT 四象限；缺失则给出可审计的占位与数据补充建议。"""
    quads = {"优势": [], "劣势": [], "机会": [], "威胁": []}
    keys = list(quads.keys())
    cur: str | None = None
    in_swot = False
    for raw in (conclusion or "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        low = line.replace(" ", "")
        if "SWOT" in low or "swot" in low:
            in_swot = True
            continue
        if in_swot or True:
            matched = None
            for k in keys:
                if k in line:
                    matched = k
                    break
            if matched:
                rest = re.sub(r"^[#*\-\s]*" + matched + r"[:：]?\s*", "", line)
                if rest:
                    quads[matched].append(rest)
                cur = matched
                continue
            if cur and (line.startswith("-") or line.startswith("*") or re.match(r"^\d+\.", line)):
                quads[cur].append(re.sub(r"^\s*[-*\d.]+\s*", "", line))
                continue
    if not any(quads.values()):
        quads["优势"].append("当前已获取受控证据，可作为归因起点。")
        quads["劣势"].append("关键业务数据缺失，定量分析能力受限。")
        quads["机会"].append("补充缺失数据源后可形成完整闭环归因。")
        quads["威胁"].append((missing_items[0] if missing_items else "数据缺失可能导致结论偏差，需人工复核。"))
    cells = "".join(
        f'<div class="swot-cell swot-{k}"><b>{k}</b><ul>'
        + "".join(f"<li>{escape(str(i))}</li>" for i in (items or ["—"]))
        + "</ul></div>"
        for k, items in quads.items()
    )
    return f'<div class="swot-grid">{cells}</div>'


def annotation_html(missing_items: list[str], manual_review_required: bool) -> str:
    """分析方法与注解：固定方法论说明 + 局限性 + 复核要求。"""
    method = (
        "<b>分析方法：</b>采用证据导向的双路受控归因（MECE）。NL2SQL 通路获取业务事实快照，"
        "RAG 通路召回规则与历史案例；两路证据按来源等级（FACT/MOCK/MISSING）标注，由 LLM 仅依据受控证据合成候选结论，不作自动责任裁决。"
    )
    limits = "<b>局限性：</b>候选结论受证据完备性约束；含 MISSING 证据或仅依赖 MOCK 时，结论仅供人工复核参考，不可作为最终处置依据。"
    review = "<b>人工复核：</b>" + ("本结果包含缺失或模拟证据，必须经业务人员复核后方可形成结论。" if manual_review_required else "建议由业务人员最终确认。")
    missing = ""
    if missing_items:
        missing = '<div class="missing-list">⚠ 待补充数据：' + "；".join(escape(str(i)) for i in missing_items) + "</div>"
    return f'<p>{method}</p><p>{limits}</p><p>{review}</p>{missing}'


_TOOL_CN = {
    "query_business_data": "业务数据查询（NL2SQL）",
    "query_knowledge_base": "知识向量召回（RAG）",
    "scenario_projection": "场景诊断投影",
    "synthesize_with_llm": "LLM 结论合成",
    "extract_keywords": "关键词抽取",
    "recall_column": "字段召回",
    "recall_metric": "指标召回",
    "recall_value": "指标取值召回",
    "merge_retrieved_info": "检索信息合并",
    "filter_table": "候选表过滤",
    "filter_metric": "候选指标过滤",
    "generate_sql": "SQL 生成",
    "validate_sql": "SQL 校验",
    "execute_sql": "SQL 执行",
    "correct_sql": "SQL 纠错",
    "self_heal_sql": "SQL 自愈",
    "add_extra_context": "上下文补充",
}
_STATUS_CN = {
    "success": "成功",
    "failed": "失败",
    "running": "运行中",
    "succeeded": "成功",
}


def _fmt_duration(ms: object) -> str:
    try:
        v = int(ms or 0)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    if v < 1000:
        return f"{v}ms"
    return f"{v / 1000:.1f}s"


def timeline_html(executions: list[dict[str, object]]) -> str:
    """思考步骤时间线：把每次工具执行按 step_no 渲染成纵向时间线。"""
    if not executions:
        return "<p>（无执行记录）</p>"
    ordered = sorted(executions, key=lambda e: int(e.get("step_no") or 0))
    items: list[str] = []
    for e in ordered:
        tool = str(e.get("tool_name", "unknown"))
        status = str(e.get("status", ""))
        status_cn = _STATUS_CN.get(status, status)
        cls = "ok" if status in {"success", "succeeded"} else ("err" if status == "failed" else "run")
        name = _TOOL_CN.get(tool, tool)
        dur = _fmt_duration(e.get("duration_ms"))
        time_str = ""
        for key in ("started_at", "finished_at"):
            val = str(e.get(key, "") or "")
            if val:
                time_str = val[11:19] if len(val) >= 19 else val
                break
        badge = f'<span class="tl-badge">{status_cn}</span>' if status else ""
        dur_html = f'<span class="tl-dur">{dur}</span>' if dur else ""
        time_html = f'<span class="tl-time">{escape(time_str)}</span>' if time_str else ""
        # 细节摘要：优先从 details 提炼
        det = e.get("details") or {}
        note = ""
        if isinstance(det, dict):
            if det.get("error_message"):
                note = escape(str(det["error_message"]))[:160]
            elif tool == "query_business_data":
                if det.get("row_count") is not None:
                    note = f"返回 {det['row_count']} 行；SQL: {escape(str(det.get('sql', '')))[:140]}"
                elif det.get("error_type"):
                    note = f"失败类型 {escape(str(det['error_type']))}：{escape(str(det.get('error_message', '')))[:120]}"
            elif tool == "query_knowledge_base":
                note = f"命中 {det.get('hit_count', 0)} 个知识片段"
            elif tool == "scenario_projection":
                note = escape(str(det.get("conclusion", "")))[:160]
            elif tool == "synthesize_with_llm":
                note = f"模型 {escape(str(det.get('model', '')))} 完成结论合成"
        items.append(
            f'<div class="tl-item {cls}"><div class="tl-dot"></div>'
            f'<div class="tl-card"><div class="tl-head"><span class="tl-step">步骤 {int(e.get("step_no") or 0)}</span>'
            f'<b>{name}</b>{badge}{dur_html}{time_html}</div>'
            + (f'<div class="tl-note">{note}</div>' if note else "")
            + "</div></div>"
        )
    return '<div class="timeline">' + "".join(items) + "</div>"


def biz_data_html(executions: list[dict[str, object]]) -> str:
    """关联业务数据：从 query_business_data 执行中提取 SQL 与结果集，结构化讲解。"""
    blocks: list[str] = []
    for e in sorted(executions, key=lambda x: int(x.get("step_no") or 0)):
        if e.get("tool_name") != "query_business_data":
            continue
        det = e.get("details") or {}
        if not isinstance(det, dict):
            continue
        status = str(e.get("status", ""))
        backend = escape(str(det.get("backend", "")))
        if status in {"success", "succeeded"}:
            rows = det.get("rows") or []
            cols = det.get("columns") or []
            sql = escape(str(det.get("sql", "")))[:1200]
            head = f"<p><b>查询通路：</b>{backend}　<b>数据行数：</b>{det.get('row_count', len(rows))} 行</p>"
            if sql:
                head += f'<div class="sql-box"><b>SQL 语句</b><pre><code>{sql}</code></pre></div>'
            if cols and rows:
                thead = "".join(f"<th>{escape(str(c))}</th>" for c in cols)
                body = ""
                for row in rows[:20]:
                    if isinstance(row, dict):
                        body += "<tr>" + "".join(f"<td>{escape(str(row.get(c, '')))}</td>" for c in cols) + "</tr>"
                    elif isinstance(row, (list, tuple)):
                        body += "<tr>" + "".join(f"<td>{escape(str(v))}</td>" for v in row) + "</tr>"
                more = f'<p class="caption">仅展示前 {min(len(rows), 20)} 行，共 {len(rows)} 行。</p>' if len(rows) > 20 else ""
                head += f'<table class="ev-table"><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>{more}'
            else:
                head += '<p class="caption">查询成功但返回空结果集。</p>'
            blocks.append(f'<div class="data-block">{head}</div>')
        else:
            err = escape(str(det.get("error_message") or det.get("error_type") or "未知错误"))[:200]
            blocks.append(
                f'<div class="data-block err"><p><b>查询通路：</b>{backend}　<b>状态：</b>失败</p>'
                f'<p class="err-text">❌ {err}</p></div>'
            )
    if not blocks:
        return '<p class="caption">本次归因未产生业务数据查询记录（可能场景未启用 NL2SQL 通路）。</p>'
    return "".join(blocks)


def vector_data_html(executions: list[dict[str, object]]) -> str:
    """关联向量数据：从 query_knowledge_base 执行中提取 RAG 命中的知识片段与相似度。"""
    blocks: list[str] = []
    for e in sorted(executions, key=lambda x: int(x.get("step_no") or 0)):
        if e.get("tool_name") != "query_knowledge_base":
            continue
        det = e.get("details") or {}
        if not isinstance(det, dict):
            continue
        query = escape(str(det.get("query", "")))
        hits = det.get("hits") or []
        status = str(e.get("status", ""))
        backend = escape(str(det.get("backend", "")))
        head = f"<p><b>召回通路：</b>{backend}　<b>命中数量：</b>{det.get('hit_count', len(hits))} 个片段</p>"
        if query:
            head += f'<p class="caption">检索问题：{query}</p>'
        if not hits:
            blocks.append(f'<div class="data-block">{head}<p class="caption">未命中任何知识片段。</p></div>')
            continue
        cards = []
        for h in hits[:10]:
            if not isinstance(h, dict):
                continue
            title = escape(str(h.get("title", "未命名片段")))
            content = escape(str(h.get("content", "")))[:400]
            score = h.get("score")
            score_html = f'<span class="score">{float(score):.0%}</span>' if isinstance(score, (int, float)) else ""
            src = escape(str(h.get("source_ref", "")))
            cls = escape(str(h.get("source_class", "MOCK")))
            tag = f'<span class="tag tag-{cls.lower()}">{cls}</span>'
            cards.append(
                f'<div class="hit-card"><div class="hit-head"><b>{title}</b>{score_html}{tag}</div>'
                f'<p>{content}</p><small>{src}</small></div>'
            )
        blocks.append(f'<div class="data-block">{head}{"".join(cards)}</div>')
    if not blocks:
        return '<p class="caption">本次归因未产生向量检索记录（可能场景未启用 RAG 通路）。</p>'
    return "".join(blocks)


class ExportRequest(BaseModel):
    question: str = ""
    conclusion: str = ""
    key_metrics: dict[str, object] = {}
    missing_items: list[str] = []
    evidence: list[dict[str, object]] = []
    executions: list[dict[str, object]] = []
    manual_review_required: bool = True
    scenario: str = "通用归因"
    style: str = "mckinsey"  # mckinsey | deloitte
    format: str = "html"  # html | pdf


HTML_TEMPLATE_MCKINSEY = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>归因分析报告</title>
<style>
@page{size:A4;margin:18mm 16mm 20mm;@bottom-center{content:"归因分析平台 · Case 运行态报告";font-size:8pt;color:#94a3b8}}
*{box-sizing:border-box}
html{-webkit-print-color-adjust:exact;print-color-adjust:exact}
body{font:10.5pt/1.7 'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;color:#1e293b;margin:0 auto;padding:48px 56px;max-width:1080px;background:#f4f7fb}
.header{border-bottom:0;border-top:6px solid #1a56db;padding:30px 34px;margin:0 0 22px;background:#fff;border-radius:0 0 14px 14px;box-shadow:0 12px 32px #0f2d6312;page-break-after:avoid}
.header h1{font-size:26pt;letter-spacing:.02em;margin:0;color:#0f2d63}
.header .meta{font-size:9pt;color:#64748b;margin-top:8px}
.section{margin-bottom:18px;padding:22px 26px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 8px 24px #0f2d6308;page-break-inside:avoid}
.section h2{font-size:13pt;color:#0f2d63;border-left:4px solid #1a56db;padding-left:10px;margin:0 0 12px;page-break-after:avoid}
.section p{margin:6px 0}
.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}
.metric-box{background:#f8fafc;border:1px solid #e2e8f0;padding:12px 14px;border-radius:6px;min-height:64px}
.metric-box .label{font-size:8.5pt;color:#64748b;text-transform:uppercase}
.metric-box .value{font-size:14pt;font-weight:700;margin-top:3px;color:#0f2d63}
.ev-table{width:100%;border-collapse:collapse;font-size:9pt;page-break-inside:auto}
.ev-table tr{page-break-inside:avoid}
.ev-table th{background:#0f2d63;color:#fff;padding:8px 10px;text-align:left}
.ev-table td{padding:8px 10px;border-bottom:1px solid #e2e8f0;vertical-align:top}
.tag{display:inline-block;padding:1px 7px;border-radius:999px;font-size:8pt;font-weight:600}
.tag-fact{background:#dcfce7;color:#047857}.tag-mock{background:#fef3c7;color:#b45309}.tag-missing{background:#fee2e2;color:#b91c1c}
.missing-list{background:#fef2f2;border-left:4px solid #b91c1c;padding:10px 14px;margin:12px 0;border-radius:0 6px 6px 0;font-size:10pt}
.review-box{background:#fffbeb;border:1px solid #fde68a;padding:12px 16px;border-radius:8px;margin-top:18px;font-size:10pt;page-break-inside:avoid}
.footer{margin-top:30px;padding-top:12px;border-top:1px solid #e2e8f0;font-size:8.5pt;color:#94a3b8;text-align:center;page-break-inside:avoid}
 .report-page{max-width:1120px;margin:0 auto;padding:48px 56px;background:#fff}.cover{min-height:235mm;display:flex;flex-direction:column;justify-content:space-between;padding:28mm 16mm 18mm;border-top:10px solid #0f2d63;page-break-after:always}.cover-kicker{color:#1a56db;font-size:10pt;font-weight:800;letter-spacing:.16em}.cover h1{max-width:700px;margin:24mm 0 8mm;font-size:35pt;line-height:1.12;color:#0f2d63}.cover p{max-width:620px;color:#64748b;font-size:13pt}.cover-meta{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding-top:18px;border-top:1px solid #cbd5e1;color:#475569;font-size:9pt}.cover-meta b{display:block;margin-top:4px;color:#0f2d63;font-size:10pt}.section{border-radius:0;border-left:4px solid #e2e8f0}.section h2{font-size:15pt;letter-spacing:.01em}.section h2:before{content:'SECTION  ';font-size:8pt;letter-spacing:.12em;color:#1a56db}.insight{display:grid;grid-template-columns:1fr 1fr;gap:14px}.insight-card{padding:15px 17px;border-top:3px solid #1a56db;background:#f8fafc}.insight-card b{display:block;color:#0f2d63}.caption{margin-top:7px;color:#64748b;font-size:8.5pt}@media print{body{padding:0;max-width:none;background:#fff}.report-page{padding:0;max-width:none}.cover{min-height:257mm}.header,.section{box-shadow:none}.section{padding:0;border:0;border-left:0;border-radius:0;margin-bottom:24px}.section{break-inside:avoid}.ev-table thead{display:table-header-group}}
.md-report h1,.md-report h2,.md-report h3{color:#0f2d63;margin:14px 0 8px}
.md-report h2{font-size:13pt;border-left:4px solid #1a56db;padding-left:8px}
.md-report h3{font-size:11.5pt}
.md-report p{margin:6px 0}.md-report ul,.md-report ol{margin:6px 0;padding-left:22px}.md-report li{margin:3px 0}
.md-report strong{color:#0f2d63}.md-report code{background:#eef2ff;padding:1px 5px;border-radius:4px;font-size:9.5pt}
.md-report hr{border:0;border-top:1px solid #e2e8f0;margin:12px 0}
.md-table{width:100%;border-collapse:collapse;font-size:9pt;margin:8px 0}.md-table th{background:#0f2d63;color:#fff;padding:6px 9px;text-align:left}.md-table td{padding:6px 9px;border:1px solid #e2e8f0}
.swot-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.swot-cell{padding:14px 16px;border-radius:8px;border-top:3px solid #1a56db;background:#f8fafc}.swot-cell b{display:block;color:#0f2d63;margin-bottom:6px;font-size:11pt}
.swot-cell ul{margin:0;padding-left:18px;font-size:9.5pt}.swot-cell li{margin:3px 0}
.swot-优势{border-top-color:#047857;background:#f0fdf4}.swot-劣势{border-top-color:#b91c1c;background:#fef2f2}.swot-机会{border-top-color:#1a56db;background:#eff6ff}.swot-威胁{border-top-color:#b45309;background:#fffbeb}
.timeline{position:relative;padding-left:26px;margin:6px 0 2px}
.timeline:before{content:"";position:absolute;left:8px;top:6px;bottom:6px;width:2px;background:linear-gradient(#1a56db,#94a3b8)}
.tl-item{position:relative;margin-bottom:10px;page-break-inside:avoid}
.tl-dot{position:absolute;left:-22px;top:5px;width:12px;height:12px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 2px #1a56db}
.tl-item.err .tl-dot{box-shadow:0 0 0 2px #b91c1c}
.tl-item.run .tl-dot{box-shadow:0 0 0 2px #b45309}
.tl-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:9px 13px}
.tl-item.err .tl-card{background:#fef2f2;border-color:#f3b6b2}
.tl-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tl-step{font-size:8pt;color:#1a56db;font-weight:800;letter-spacing:.06em}
.tl-badge{display:inline-block;padding:0 6px;border-radius:999px;font-size:7.5pt;font-weight:700;background:#dcfce7;color:#047857}
.tl-item.err .tl-badge{background:#fee2e2;color:#b91c1c}
.tl-item.run .tl-badge{background:#fef3c7;color:#b45309}
.tl-dur,.tl-time{font-size:8pt;color:#94a3b8}
.tl-note{margin-top:5px;font-size:9pt;color:#475569;word-break:break-all}
.data-block{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:11px 14px;margin:8px 0;page-break-inside:avoid}
.data-block.err{background:#fef2f2;border-color:#f3b6b2}
.data-block b{color:#0f2d63}
.sql-box{background:#0f172a;color:#e2e8f0;border-radius:6px;padding:9px 12px;margin:7px 0;font-size:8.5pt}
.sql-box pre{margin:0;white-space:pre-wrap;word-break:break-all}
.sql-box code{font-family:ui-monospace,Consolas,monospace;color:#93c5fd}
.hit-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:9px 12px;margin:7px 0;page-break-inside:avoid}
.hit-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px}
.hit-head b{color:#0f2d63}
.score{display:inline-block;padding:0 7px;border-radius:999px;background:#eff6ff;color:#1a56db;font-size:8.5pt;font-weight:800}
.hit-card p{margin:4px 0;font-size:9pt;color:#475569}
.hit-card small{color:#94a3b8;font-size:8pt}
.err-text{color:#b91c1c}
.caption{font-size:8.5pt;color:#64748b}
</style></head><body>
<div class="cover" style="min-height:235mm;display:flex;flex-direction:column;justify-content:space-between;padding:28mm 16mm 18mm;border-top:10px solid #0f2d63;page-break-after:always"><div><div style="color:#1a56db;font-size:10pt;font-weight:800;letter-spacing:.16em">ATTRIBUTION ANALYSIS · EXECUTIVE REPORT</div><h1 style="margin:24mm 0 8mm;font-size:35pt;line-height:1.12;color:#0f2d63">归因分析报告</h1><p style="color:#64748b;font-size:13pt">以事实、证据和可执行行动，回答经营问题。</p></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding-top:18px;border-top:1px solid #cbd5e1;color:#475569;font-size:9pt"><div>分析场景<br><b style="color:#0f2d63">{scenario}</b></div><div>生成时间<br><b style="color:#0f2d63">{generated_at}</b></div><div>报告方法<br><b style="color:#0f2d63">MECE · Evidence-led</b></div></div></div>
<div class="header">
<h1>归因分析报告</h1>
<div class="meta">场景: {scenario} | 生成时间: {generated_at} | 风格: McKinsey</div>
</div>
<div class="section">
<h2>分析问题</h2>
<p>{question}</p>
</div>
<div class="section">
<h2>关键指标</h2>
<div class="metric-grid">{metrics_html}</div>
</div>
<div class="section">
<h2>思考步骤时间线</h2>
<p class="caption">归因分析的完整执行轨迹：每一步的工具调用、状态与耗时，可完整追溯"来龙去脉"。</p>
{timeline_html}
</div>
<div class="section">
<h2>关联业务数据</h2>
<p class="caption">NL2SQL 通路查询到的业务事实快照：SQL 语句与返回结果集。</p>
{biz_data_html}
</div>
<div class="section">
<h2>关联向量数据</h2>
<p class="caption">RAG 通路召回的知识片段：命中文档、相似度得分与来源定位。</p>
{vector_data_html}
</div>
<div class="section">
<h2>归因结论</h2>
<div class="md-report">{conclusion}</div>
</div>
<div class="section">
<h2>SWOT 分析</h2>
{swot_html}
</div>
<div class="section">
<h2>分析方法与注解</h2>
{annotation_html}
</div>
<div class="section">
<h2>证据链</h2>
<table class="ev-table"><thead><tr><th>来源等级</th><th>内容摘要</th><th>来源定位</th></tr></thead><tbody>
{evidence_rows}
</tbody></table>
</div>
<div class="review-box">
{review_text}
</div>
<div class="footer">本报告由归因分析平台自动生成。证据等级: FACT=可验证事实, MOCK=模拟数据, MISSING=缺失。关键结论含 MISSING 或仅依赖 MOCK 时必须人工复核。</div>
</body></html>"""


HTML_TEMPLATE_DELOITTE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>归因分析报告</title>
<style>
@page{size:A4;margin:1.5cm}
body{font:11pt/1.6 'Helvetica Neue','PingFang SC','Microsoft YaHei',sans-serif;color:#1e293b;margin:0 auto;padding:48px 56px;max-width:1080px;background:#f4f7fb}
.header{background:linear-gradient(135deg,#0f172a,#172554);color:#fff;padding:30px 34px;border-radius:14px;margin-bottom:18px;box-shadow:0 12px 32px #0f172a22}
.header h1{font-size:20pt;margin:0}
.header .meta{font-size:10pt;color:#cbd5e1;margin-top:6px}
.traffic-light{display:flex;gap:12px;align-items:center;margin:0 0 18px;padding:18px 24px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 8px 24px #0f172a0d}
.light{width:40px;height:40px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:14pt;color:#fff}
.light-red{background:#b91c1c}
.light-yellow{background:#b45309}
.light-green{background:#047857}
.section{margin-bottom:18px;padding:22px 26px;background:#fff;border:1px solid #e2e8f0;border-radius:14px;box-shadow:0 8px 24px #0f172a0d}
.section h2{font-size:13pt;color:#0f172a;border-bottom:2px solid #0f172a;padding-bottom:4px;margin:0 0 10px}
.evidence-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;margin:6px 0}
.evidence-card .tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:9pt;font-weight:700;margin-right:8px}
.tag-fact{background:#dcfce7;color:#047857}
.tag-mock{background:#fef3c7;color:#b45309}
.tag-missing{background:#fee2e2;color:#b91c1c}
.missing-block{background:#fee2e2;border-left:5px solid #b91c1c;padding:10px 14px;margin:8px 0;border-radius:0 6px 6px 0}
.review-block{background:#fffbeb;border:2px solid #fde68a;padding:12px 16px;border-radius:8px;margin-top:16px}
.metric-row{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}
.metric-item{background:#eff6ff;padding:8px 12px;border-radius:6px;flex:1;min-width:120px}
.metric-item .label{font-size:9pt;color:#64748b;font-weight:600;text-transform:uppercase}
.metric-item .value{font-size:13pt;font-weight:700;margin-top:2px;color:#1a56db}
.footer{margin-top:24px;padding:12px 30px;border-top:1px solid #e2e8f0;font-size:9pt;color:#94a3b8;text-align:center}
@media print{body{padding:0;max-width:none;background:#fff}.header,.traffic-light,.section{box-shadow:none}.section{padding:0;border:0;border-radius:0;margin-bottom:18px}}
.md-report h1,.md-report h2,.md-report h3{color:#0f2d63;margin:14px 0 8px}
.md-report h2{font-size:13pt;border-left:4px solid #1a56db;padding-left:8px}
.md-report h3{font-size:11.5pt}
.md-report p{margin:6px 0}.md-report ul,.md-report ol{margin:6px 0;padding-left:22px}.md-report li{margin:3px 0}
.md-report strong{color:#0f2d63}.md-report code{background:#eef2ff;padding:1px 5px;border-radius:4px;font-size:9.5pt}
.md-report hr{border:0;border-top:1px solid #e2e8f0;margin:12px 0}
.md-table{width:100%;border-collapse:collapse;font-size:9pt;margin:8px 0}.md-table th{background:#0f2d63;color:#fff;padding:6px 9px;text-align:left}.md-table td{padding:6px 9px;border:1px solid #e2e8f0}
.swot-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.swot-cell{padding:14px 16px;border-radius:8px;border-top:3px solid #1a56db;background:#f8fafc}.swot-cell b{display:block;color:#0f2d63;margin-bottom:6px;font-size:11pt}
.swot-cell ul{margin:0;padding-left:18px;font-size:9.5pt}.swot-cell li{margin:3px 0}
.swot-优势{border-top-color:#047857;background:#f0fdf4}.swot-劣势{border-top-color:#b91c1c;background:#fef2f2}.swot-机会{border-top-color:#1a56db;background:#eff6ff}.swot-威胁{border-top-color:#b45309;background:#fffbeb}
.timeline{position:relative;padding-left:26px;margin:6px 0 2px}
.timeline:before{content:"";position:absolute;left:8px;top:6px;bottom:6px;width:2px;background:linear-gradient(#1a56db,#94a3b8)}
.tl-item{position:relative;margin-bottom:10px;page-break-inside:avoid}
.tl-dot{position:absolute;left:-22px;top:5px;width:12px;height:12px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 2px #1a56db}
.tl-item.err .tl-dot{box-shadow:0 0 0 2px #b91c1c}
.tl-item.run .tl-dot{box-shadow:0 0 0 2px #b45309}
.tl-card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:9px 13px}
.tl-item.err .tl-card{background:#fef2f2;border-color:#f3b6b2}
.tl-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.tl-step{font-size:8pt;color:#1a56db;font-weight:800;letter-spacing:.06em}
.tl-badge{display:inline-block;padding:0 6px;border-radius:999px;font-size:7.5pt;font-weight:700;background:#dcfce7;color:#047857}
.tl-item.err .tl-badge{background:#fee2e2;color:#b91c1c}
.tl-item.run .tl-badge{background:#fef3c7;color:#b45309}
.tl-dur,.tl-time{font-size:8pt;color:#94a3b8}
.tl-note{margin-top:5px;font-size:9pt;color:#475569;word-break:break-all}
.data-block{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:11px 14px;margin:8px 0;page-break-inside:avoid}
.data-block.err{background:#fef2f2;border-color:#f3b6b2}
.data-block b{color:#0f2d63}
.sql-box{background:#0f172a;color:#e2e8f0;border-radius:6px;padding:9px 12px;margin:7px 0;font-size:8.5pt}
.sql-box pre{margin:0;white-space:pre-wrap;word-break:break-all}
.sql-box code{font-family:ui-monospace,Consolas,monospace;color:#93c5fd}
.hit-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:9px 12px;margin:7px 0;page-break-inside:avoid}
.hit-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px}
.hit-head b{color:#0f2d63}
.score{display:inline-block;padding:0 7px;border-radius:999px;background:#eff6ff;color:#1a56db;font-size:8.5pt;font-weight:800}
.hit-card p{margin:4px 0;font-size:9pt;color:#475569}
.hit-card small{color:#94a3b8;font-size:8pt}
.err-text{color:#b91c1c}
.caption{font-size:8.5pt;color:#64748b}
</style></head><body>
<div class="cover" style="min-height:235mm;display:flex;flex-direction:column;justify-content:space-between;padding:28mm 16mm 18mm;border-top:10px solid #0f2d63;page-break-after:always"><div><div style="color:#1a56db;font-size:10pt;font-weight:800;letter-spacing:.16em">ATTRIBUTION ANALYSIS · EXECUTIVE REPORT</div><h1 style="margin:24mm 0 8mm;font-size:35pt;line-height:1.12;color:#0f2d63">归因分析报告</h1><p style="color:#64748b;font-size:13pt">以事实、证据和可执行行动，回答经营问题。</p></div><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;padding-top:18px;border-top:1px solid #cbd5e1;color:#475569;font-size:9pt"><div>分析场景<br><b style="color:#0f2d63">{scenario}</b></div><div>生成时间<br><b style="color:#0f2d63">{generated_at}</b></div><div>报告方法<br><b style="color:#0f2d63">MECE · Evidence-led</b></div></div></div>
<div class="header">
<h1>归因分析报告</h1>
<div class="meta">场景: {scenario} | 生成时间: {generated_at} | 风格: Deloitte</div>
</div>
<div class="traffic-light">{traffic_light}</div>
<div class="section">
<h2>分析问题</h2>
<p>{question}</p>
</div>
<div class="section">
<h2>关键指标</h2>
<div class="metric-row">{metrics_html}</div>
</div>
<div class="section">
<h2>思考步骤时间线</h2>
<p class="caption">归因分析的完整执行轨迹：每一步的工具调用、状态与耗时，可完整追溯"来龙去脉"。</p>
{timeline_html}
</div>
<div class="section">
<h2>关联业务数据</h2>
<p class="caption">NL2SQL 通路查询到的业务事实快照：SQL 语句与返回结果集。</p>
{biz_data_html}
</div>
<div class="section">
<h2>关联向量数据</h2>
<p class="caption">RAG 通路召回的知识片段：命中文档、相似度得分与来源定位。</p>
{vector_data_html}
</div>
<div class="section">
<h2>归因结论</h2>
<div class="md-report">{conclusion}</div>
</div>
<div class="section">
<h2>SWOT 分析</h2>
{swot_html}
</div>
<div class="section">
<h2>分析方法与注解</h2>
{annotation_html}
</div>
<div class="section">
<h2>证据链</h2>
{evidence_cards}
</div>
<div class="review-block">
{review_text}
</div>
<div class="footer">Deloitte 风格报告 | 归因分析平台自动生成 | 证据等级: FACT/MOCK/MISSING | 关键结论含 MISSING 时必须人工复核</div>
</body></html>"""


@router.post("/report")
def export_report(
    payload: ExportRequest,
    subject: SubjectContext = Depends(current_subject),
) -> Response:
    """导出归因分析报告为 HTML。"""
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # 指标 HTML
    metrics_html = ""
    for k, v in (payload.key_metrics or {}).items():
        metrics_html += f'<div class="metric-box"><div class="label">{k}</div><div class="value">{v}</div></div>' if payload.style == "mckinsey" else f'<div class="metric-item"><div class="label">{k}</div><div class="value">{v}</div></div>'

    # 缺失项 HTML
    missing_html = ""
    if payload.missing_items:
        items = "；".join(payload.missing_items)
        missing_html = f'<div class="missing-list">⚠ 待补充数据：{items}</div>' if payload.style == "mckinsey" else f'<div class="missing-block">⚠ 待补充数据：{items}</div>'

    # 证据 HTML
    evidence_rows = ""
    evidence_cards = ""
    for ev in (payload.evidence or []):
        cls = str(ev.get("source_class", "MOCK")).lower()
        tag_class = f"tag-{cls}"
        summary = str(ev.get("content_summary", ""))[:200]
        ref = str(ev.get("source_ref", ""))
        rule = str(ev.get("rule_version", ""))
        evidence_rows += f'<tr><td><span class="tag {tag_class}">{ev.get("source_class","MOCK")}</span></td><td>{summary}</td><td>{ref} {rule}</td></tr>'
        evidence_cards += f'<div class="evidence-card"><span class="tag {tag_class}">{ev.get("source_class","MOCK")}</span>{summary}<br><small style="color:#94a3b8">{ref} {rule}</small></div>'

    # 复核提示
    review_text = "⚠ 当前结果包含模拟或缺失证据，必须经人工复核；不形成自动处置或责任裁决。" if payload.manual_review_required else "评估完成，建议由业务人员最终确认。"

    # 红绿灯
    has_missing = bool(payload.missing_items)
    has_fact = any(str(ev.get("source_class", "")).upper() == "FACT" for ev in (payload.evidence or []))
    if has_missing:
        light = '<div class="light light-red">!</div><div style="line-height:40px;color:#b91c1c;font-weight:700">需人工复核（缺失数据）</div>'
    elif not has_fact:
        light = '<div class="light light-yellow">!</div><div style="line-height:40px;color:#b45309;font-weight:700">仅模拟数据，建议复核</div>'
    else:
        light = '<div class="light light-green">✓</div><div style="line-height:40px;color:#047857;font-weight:700">证据充分</div>'

    template = HTML_TEMPLATE_MCKINSEY if payload.style == "mckinsey" else HTML_TEMPLATE_DELOITTE
    conclusion_html = md_to_html(payload.conclusion)
    swot = swot_html(payload.conclusion, payload.missing_items)
    annotation = annotation_html(payload.missing_items, payload.manual_review_required)
    timeline = timeline_html(payload.executions or [])
    biz = biz_data_html(payload.executions or [])
    vector = vector_data_html(payload.executions or [])
    html = (template
        .replace("{scenario}", payload.scenario)
        .replace("{generated_at}", generated_at)
        .replace("{question}", payload.question or "（未提供问题描述）")
        .replace("{metrics_html}", metrics_html)
        .replace("{conclusion}", conclusion_html)
        .replace("{missing_html}", missing_html)
        .replace("{evidence_rows}", evidence_rows)
        .replace("{evidence_cards}", evidence_cards)
        .replace("{review_text}", review_text)
        .replace("{traffic_light}", light)
        .replace("{swot_html}", swot)
        .replace("{annotation_html}", annotation)
        .replace("{timeline_html}", timeline)
        .replace("{biz_data_html}", biz)
        .replace("{vector_data_html}", vector)
    )

    return Response(
        content=html,
        media_type="text/html",
        headers={"Content-Disposition": f'attachment; filename="attribution_report_{payload.style}.html"'},
    )


def _case_report_response(case, subject: SubjectContext, style: str, result_version: int | None = None) -> Response:
    """从主体可见 Case 的指定 Result 版本生成报告，禁止前端注入结论。"""
    if style not in {"mckinsey", "deloitte"}:
        raise HTTPException(status_code=422, detail="style must be mckinsey or deloitte")
    result = next((item for item in case.results if result_version is None or item.version_no == result_version), None)
    if result is None:
        raise HTTPException(status_code=404, detail="result version not found")
    result_data = result_payload(result)
    evidence = [evidence_payload(item) for item in case.evidence if item.evidence_id in result_data["evidence_ids"]]
    executions = [execution_payload(item, case.evidence) for item in case.executions]
    response = export_report(
        ExportRequest(
            question=escape(result_data["question"]),
            conclusion=result_data["conclusion"],
            key_metrics={str(item.get("name", "指标")): item.get("value", "—") for item in result_data["key_metrics"]},
            missing_items=[escape(item) for item in result_data["missing_items"]],
            evidence=[{key: escape(value) if isinstance(value, str) else value for key, value in item.items()} for item in evidence],
            executions=executions,
            manual_review_required=bool(result_data["manual_review_required"]),
            scenario=case.scenario_hint or "通用归因",
            style=style,
        ),
        subject,
    )
    report_audit.append({"case_id": case.case_id, "result_id": result_data["result_id"], "result_version": str(result_data["version_no"]), "subject_id": subject.subject_id, "style": style, "created_at": datetime.now(UTC).isoformat()})
    response.headers["Content-Disposition"] = f'inline; filename="case_{case.case_id}_result_{result_data["version_no"]}_{style}.html"'
    response.headers["X-Report-Case-Id"] = case.case_id
    response.headers["X-Report-Result-Version"] = str(result_data["version_no"])
    return response


@router.get("/reports")
def list_reports(subject: SubjectContext = Depends(current_subject)) -> dict[str, object]:
    """列出当前主体全部 Case 的全部 Result 版本，报告目录不依赖进程内审计。"""
    reports = []
    for case in service.list_cases(subject.subject_id):
        for result in case.results:
            item = result_payload(result)
            reports.append({
                "case_id": case.case_id,
                "question": case.question,
                "scenario": case.scenario_hint or "通用归因",
                "result_id": item["result_id"],
                "version_no": item["version_no"],
                "status": item["status"],
                "created_at": item["created_at"],
                "manual_review_required": item["manual_review_required"],
                "evidence_count": len(item["evidence_ids"]),
            })
    reports.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return {"data": reports}


@router.get("/cases/{case_id}/results/{version_no}/report")
def export_case_result_report(case_id: str, version_no: int, style: str = "mckinsey", subject: SubjectContext = Depends(current_subject)) -> Response:
    """打开指定 Case 的指定 Result 版本；Case 与主体同时校验。"""
    try:
        case = service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return _case_report_response(case, subject, style, version_no)


@router.get("/cases/{case_id}/report")
def export_case_report(
    case_id: str,
    style: str = "mckinsey",
    subject: SubjectContext = Depends(current_subject),
) -> Response:
    """Render the latest HTML-first report from a subject-owned Case."""
    if style not in {"mckinsey", "deloitte"}:
        raise HTTPException(status_code=422, detail="style must be mckinsey or deloitte")
    try:
        case = service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    if not case.results:
        raise HTTPException(status_code=409, detail="case has no reportable result")
    response = _case_report_response(case, subject, style)
    response.headers["Content-Disposition"] = f'attachment; filename="case_{case_id}_{style}.html"'
    return response


@router.get("/cases/{case_id}/report-audit")
def list_report_audit(case_id: str, subject: SubjectContext = Depends(current_subject)) -> dict[str, object]:
    """Return the current subject's in-process report delivery audit records for one Case."""
    try:
        service.get_case(case_id, subject.subject_id)
    except CaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail="case not found") from exc
    return {"data": [item for item in report_audit if item["case_id"] == case_id and item["subject_id"] == subject.subject_id]}
