"""证据工具：将两条独立检索路径归并为统一 Evidence 输入。"""
from __future__ import annotations

from dataclasses import dataclass, field

from time import perf_counter

from attribution_analysis.ports.evidence import NL2SQLPort, RAGPort


@dataclass(frozen=True)
class CollectedEvidence:
    tool_name: str
    source_class: str
    source_ref: str
    rule_version: str
    content_summary: str
    details: dict[str, object] = field(default_factory=dict)
    failure_class: str | None = None
    duration_ms: int = 0


def _summarize_rows(rows: list, columns: list, max_rows: int = 3, max_cell: int = 80) -> str:
    """把前 N 行关键列值压成可读字符串，让 LLM 直接从 summary 拿到数值而非只看到行数。"""
    if not rows:
        return "无记录"
    sample = list(rows)[:max_rows]
    parts: list[str] = []
    for row in sample:
        cells: list[str] = []
        if isinstance(row, dict):
            # QueryResult.rows 约定为行对象（dict）：按列名取值
            for col in columns:
                if col not in row:
                    continue
                value = row[col]
                text = "NULL" if value is None else str(value)
                if len(text) > max_cell:
                    text = text[: max_cell - 3] + "..."
                cells.append(f"{col}={text}")
        else:
            # 兼容位置索引的行序列（list/tuple）
            for idx, col in enumerate(columns):
                if idx >= len(row):
                    break
                value = row[idx]
                text = "NULL" if value is None else str(value)
                if len(text) > max_cell:
                    text = text[: max_cell - 3] + "..."
                cells.append(f"{col}={text}")
        parts.append("{" + ", ".join(cells) + "}")
    suffix = f" ...+{len(rows) - len(sample)} 行" if len(rows) > len(sample) else ""
    return " | ".join(parts) + suffix


def _summarize_hits(hits, max_hits: int = 2, max_content: int = 120) -> str:
    """把前 N 个 RAG 命中片段的标题与内容预览压成可读字符串。"""
    if not hits:
        return "无命中"
    sample = list(hits)[:max_hits]
    parts: list[str] = []
    for hit in sample:
        title = getattr(hit, "title", "") or ""
        content = getattr(hit, "content", "") or ""
        if len(content) > max_content:
            content = content[: max_content - 3] + "..."
        parts.append(f"[{title}] {content}")
    return " || ".join(parts)


class EvidenceToolset:
    """RAG 与 NL2SQL 只共享输出契约，不共享实现或失败边界。"""

    def __init__(self, rag: RAGPort, nl2sql: NL2SQLPort) -> None:
        """绑定 RAG 与 NL2SQL 端口实现。"""
        self.rag = rag
        self.nl2sql = nl2sql

    def collect(self, question: str) -> tuple[CollectedEvidence, ...]:
        """收集两条独立证据：NL2SQL 业务数据 + RAG 知识检索。

        任一路径失败不阻塞另一条，返回带 MISSING 标记的证据。
        """
        return (self._collect_business(question), self._collect_knowledge(question))

    def _collect_business(self, question: str) -> CollectedEvidence:
        """NL2SQL 通路：查业务数据，失败降级为 MISSING 证据。"""
        started = perf_counter()
        try:
            business = self.nl2sql.query(question)
        except Exception as exc:  # 外部读取失败不阻塞另一条独立证据通路。
            return CollectedEvidence(
                tool_name="query_business_data",
                source_class="MISSING",
                source_ref="dependency.nl2sql.unavailable",
                rule_version="none",
                content_summary="受控业务数据查询失败，需补充可用的数据源或稍后重试。",
                details={"backend": "unavailable", "called": True, "error_type": type(exc).__name__, "error_message": str(exc), "sql": None, "parameters": [], "columns": [], "rows": [], "row_count": 0},
                failure_class=type(exc).__name__,
                duration_ms=round((perf_counter() - started) * 1000),
            )
        rows_preview = _summarize_rows(list(business.rows), list(business.columns))
        return CollectedEvidence(
            tool_name="query_business_data",
            source_class=business.source_class,
            source_ref=business.source_ref,
            rule_version="nl2sql.v1",
            content_summary=f"受控查询返回 {len(business.rows)} 条业务记录（{business.source_ref}）；样例：{rows_preview}。",
            details={"backend": business.source_ref, "called": True, "sql": business.sql, "parameters": list(business.params), "columns": list(business.columns), "rows": list(business.rows), "row_count": len(business.rows), "source_ref": business.source_ref},
            duration_ms=round((perf_counter() - started) * 1000),
        )

    def _collect_knowledge(self, question: str) -> CollectedEvidence:
        """RAG 通路：检索手册/政策，失败降级为 MISSING 证据。"""
        started = perf_counter()
        try:
            knowledge = self.rag.retrieve(question)
        except Exception as exc:  # 与 NL2SQL 失败边界分离，保留可用业务证据。
            return CollectedEvidence(
                tool_name="query_knowledge_base",
                source_class="MISSING",
                source_ref="dependency.rag.unavailable",
                rule_version="none",
                content_summary="知识库检索失败，需补充可用手册、政策或稍后重试。",
                details={"backend": "unavailable", "called": True, "query": question, "error_type": type(exc).__name__, "error_message": str(exc), "hits": [], "hit_count": 0},
                failure_class=type(exc).__name__,
                duration_ms=round((perf_counter() - started) * 1000),
            )
        knowledge_refs = ", ".join(hit.source_ref for hit in knowledge) or "无命中"
        hits_preview = _summarize_hits(knowledge)
        return CollectedEvidence(
            tool_name="query_knowledge_base",
            source_class=(knowledge[0].source_class if knowledge else "MISSING"),
            source_ref=(knowledge[0].source_ref if knowledge else "dependency.rag.no_match"),
            rule_version="rag.v1",
            content_summary=f"知识检索命中 {len(knowledge)} 个片段；来源：{knowledge_refs}；预览：{hits_preview}。",
            details={"backend": (knowledge[0].source_ref if knowledge else "no_match"), "called": True, "query": question, "hit_count": len(knowledge), "hits": [{"title": hit.title, "content": hit.content, "source_ref": hit.source_ref, "score": hit.score, "source_class": hit.source_class} for hit in knowledge]},
            duration_ms=round((perf_counter() - started) * 1000),
        )
