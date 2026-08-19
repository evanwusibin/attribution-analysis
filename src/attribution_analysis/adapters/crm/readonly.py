"""CRM 只读适配器：通过 DuckDB ATTACH 瑞能 CRM SQLite 库，仅暴露 6 个白名单语义视图和 4 个计算工具。

对齐 03_技术方案与架构.md 第七节：
- CRM 真实库只读访问：ATTACH (TYPE sqlite, READ_ONLY)；
- 6 个白名单语义视图绑定列 + 行数上限 + 只读校验；
- 所有结果携带 source_class/source_ref/rule_version，供 Evidence 回溯源；
- 竞品/行业基准等外部数据不可得时返回 MISSING。

本模块是从 adapters/crm/demo.py 拆分出的「真实库」实现（FACT 证据）；
模拟库实现见 adapters/crm/demo_adapter.py。
"""
from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

from duckdb import DuckDBPyConnection

from attribution_analysis.ports.crm import (
    CRMPort,
    CustomerActivityRow,
    FunnelConversionResult,
    ChurnScoreResult,
    LeadQualityRow,
    LeadSourceAnalysisResult,
    OpportunityFollowupRow,
    OpportunityFunnelRow,
    QuoteCompetitivenessRow,
    QuoteDeviationResult,
    SalesPerformanceRow,
)

CRM_DB_PATH = os.environ.get("ATTRIBUTION_CRM_DB_PATH") or ""
SOURCE_REF = "crm.ruien.realtime.v1"
SOURCE_CLASS = "FACT"
RULE_VERSION = "crm.view.v1"


class CrmSchemaError(RuntimeError):
    """CRM semantic-view contract is not available or not complete."""


class CrmReadonlyAdapter(CRMPort):
    """CRM 只读适配器：只允许访问已验收的语义视图。"""

    SEMANTIC_VIEWS = (
        "v_opportunities", "v_customers", "v_field_visits",
        "v_quotes", "v_contracts", "v_leads",
    )

    def __init__(self, connection: DuckDBPyConnection | None = None, db_path: str | None = None) -> None:
        """绑定已有连接或按路径 ATTACH 瑞能 CRM 库（只读）。

        db_path 未显式传入时读取环境变量 ATTRIBUTION_CRM_DB_PATH；
        未配置时抛 CrmSchemaError，避免把某台机器的绝对路径当作默认值。
        """
        resolved_path = db_path if db_path is not None else CRM_DB_PATH
        self._owns_connection = connection is None
        self.connection = connection or self._attach(resolved_path)

    @staticmethod
    def _attach(db_path: str) -> DuckDBPyConnection:
        """ATTACH 瑞能 CRM SQLite 库并创建语义视图，返回内存 DuckDB 连接。"""
        if not db_path:
            raise CrmSchemaError(
                "ATTRIBUTION_CRM_DB_PATH is not configured; "
                "set it in local .env to enable the S9 presales FACT adapter."
            )
        path = Path(db_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"CRM database does not exist: {path}")
        if ".." in path.parts:
            raise CrmSchemaError(f"CRM database path escapes the allowed root: {path}")
        import duckdb
        connection = duckdb.connect(":memory:")
        escaped_path = str(path).replace("'", "''")
        if "'" in str(path):
            raise CrmSchemaError(f"CRM database path contains a quote character: {path}")
        connection.execute(f"ATTACH '{escaped_path}' AS crm (TYPE sqlite, READ_ONLY)")
        CrmReadonlyAdapter._create_semantic_views(connection)
        return connection

    @staticmethod
    def _create_semantic_views(connection: DuckDBPyConnection) -> None:
        """把已确认的 CRM 基础表投影为本地只读语义视图。"""
        source_tables = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables"
            ).fetchall()
        }
        required_tables = {
            "customers", "opportunities", "contracts", "sales_orders",
            "field_visits", "sales_persons",
        }
        missing = sorted(required_tables - source_tables)
        if missing:
            # 空库仍可构造适配器，让 require_semantic_views 在查询边界报告契约缺失。
            # 这样连接生命周期测试和实际查询失败路径保持可观测且可关闭。
            return
        views = {
            "v_opportunities": """
                SELECT id, customer_id, owner_id, stage, amount, created_at,
                       product_category, competitors
                FROM crm.opportunities
            """,
            "v_customers": """
                SELECT id AS customer_id, name, COALESCE(region, '未知') AS region, source
                FROM crm.customers
            """,
            "v_field_visits": """
                SELECT opportunity_id, customer_id, visit_date, visit_type,
                       SUBSTRING(COALESCE(content, ''), 1, 200) AS content
                FROM crm.field_visits
            """,
            "v_quotes": """
                SELECT id AS opportunity_id, customer_id, amount AS our_quote,
                       competitors
                FROM crm.opportunities
            """,
            "v_contracts": """
                SELECT id, customer_id, sign_date, amount
                FROM crm.contracts
            """,
            "v_sales_orders": """
                SELECT owner_id, order_date, amount, received_amount
                FROM crm.sales_orders
            """,
            "v_sales_persons": """
                SELECT id, name, COALESCE(dept_name, '未知') AS dept_name,
                       CASE WHEN is_active IN ('1', '在职', 'active') THEN '1' ELSE is_active END AS is_active
                FROM crm.sales_persons
            """,
            "v_leads": """
                SELECT id AS customer_id, source
                FROM crm.customers
                WHERE source IS NOT NULL AND source != '' AND source != 'NULL'
            """,
        }
        for name, query in views.items():
            connection.execute(f"CREATE OR REPLACE VIEW {name} AS {query}")

    def __enter__(self) -> "CrmReadonlyAdapter":
        """上下文入口：校验语义视图存在后返回自身。"""
        self.require_semantic_views()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """上下文出口：关闭自有连接。"""
        self.close()

    def close(self) -> None:
        """关闭自有连接（外部传入的连接不关闭）。"""
        if self._owns_connection:
            self.connection.close()

    def require_semantic_views(self) -> None:
        """校验 6 个语义视图可用；缺失时抛 CrmSchemaError。"""
        available = {
            row[0]
            for row in self.connection.execute(
                "SELECT view_name FROM duckdb_views() WHERE schema_name = 'main'"
            ).fetchall()
        }
        missing = tuple(view for view in self.SEMANTIC_VIEWS if view not in available)
        if missing:
            raise CrmSchemaError("CRM semantic views are not validated: " + ", ".join(missing))

    def _not_implemented(self, operation: str) -> None:
        """未验收视图映射的兜底：抛契约缺失错误。"""
        self.require_semantic_views()
        raise CrmSchemaError(f"{operation} requires approved CRM view column mappings")

    def query_opportunity_funnel(self, region: str | None = None, stage: str | None = None) -> tuple[OpportunityFunnelRow, ...]:
        """商机漏斗视图：按区域/阶段过滤，返回商机及阶段停留天数。"""
        self.require_semantic_views()
        sql = "SELECT o.id, o.customer_id, o.owner_id, o.stage, o.amount, o.created_at FROM v_opportunities o"
        clauses = ["1=1"]
        params: list[str] = []
        if region:
            clauses.append("o.customer_id IN (SELECT customer_id FROM v_customers WHERE region = ?)")
            params.append(region)
        if stage:
            clauses.append("o.stage = ?")
            params.append(stage)
        rows = self.connection.execute(sql + " WHERE " + " AND ".join(clauses) + " ORDER BY o.created_at DESC LIMIT 500", params).fetchall()
        return tuple(
            OpportunityFunnelRow(r[0], r[1], r[2], r[3], float(r[4] or 0), self._days_between(r[5]), SOURCE_CLASS, SOURCE_REF, RULE_VERSION)
            for r in rows
        )

    def query_opportunity_followups(self, opportunity_id: str | None = None, customer_id: str | None = None) -> tuple[OpportunityFollowupRow, ...]:
        """跟进记录视图：按商机或客户过滤拜访记录。"""
        self.require_semantic_views()
        clauses = ["1=1"]
        params: list[str] = []
        if opportunity_id:
            clauses.append("opportunity_id = ?")
            params.append(opportunity_id)
        if customer_id:
            clauses.append("customer_id = ?")
            params.append(customer_id)
        rows = self.connection.execute(
            "SELECT opportunity_id, customer_id, visit_date, visit_type, content FROM v_field_visits WHERE "
            + " AND ".join(clauses) + " ORDER BY visit_date DESC LIMIT 500", params,
        ).fetchall()
        return tuple(OpportunityFollowupRow(r[0], r[1], str(r[2]), r[3], r[4], SOURCE_CLASS, SOURCE_REF, RULE_VERSION) for r in rows)

    def query_customer_activity(self, customer_id: str | None = None, region: str | None = None) -> tuple[CustomerActivityRow, ...]:
        """客户活跃度视图：跟进/拜访/合同聚合，按客户或区域过滤。"""
        self.require_semantic_views()
        clauses = ["1=1"]
        params: list[str] = []
        if customer_id:
            clauses.append("customer_id = ?")
            params.append(customer_id)
        if region:
            clauses.append("region = ?")
            params.append(region)
        customers = self.connection.execute(
            "SELECT customer_id, name, region FROM v_customers WHERE " + " AND ".join(clauses) + " LIMIT 500", params,
        ).fetchall()
        result: list[CustomerActivityRow] = []
        for cid, name, customer_region in customers:
            contact_30 = self.connection.execute("SELECT COUNT(*) FROM v_field_visits WHERE customer_id = ? AND visit_date >= CURRENT_DATE - INTERVAL 30 DAY", [cid]).fetchone()[0]
            contact_90 = self.connection.execute("SELECT COUNT(*) FROM v_field_visits WHERE customer_id = ? AND visit_date >= CURRENT_DATE - INTERVAL 90 DAY", [cid]).fetchone()[0]
            visits_90 = self.connection.execute("SELECT COUNT(*) FROM v_field_visits WHERE customer_id = ? AND visit_type = '拜访' AND visit_date >= CURRENT_DATE - INTERVAL 90 DAY", [cid]).fetchone()[0]
            contracts_12 = self.connection.execute("SELECT COUNT(*) FROM v_contracts WHERE customer_id = ? AND sign_date >= CURRENT_DATE - INTERVAL 365 DAY", [cid]).fetchone()[0]
            last_contact = self.connection.execute("SELECT MAX(visit_date) FROM v_field_visits WHERE customer_id = ?", [cid]).fetchone()[0]
            result.append(CustomerActivityRow(cid, name, customer_region, int(contact_30), int(contact_90), int(visits_90), int(contracts_12), str(last_contact) if last_contact else None, SOURCE_CLASS, SOURCE_REF, RULE_VERSION))
        return tuple(result)

    def query_sales_performance(self, sales_person_id: str | None = None, region: str | None = None) -> tuple[SalesPerformanceRow, ...]:
        """业绩视图：月/年度目标-签约-回款，按销售员或部门过滤。"""
        self.require_semantic_views()
        clauses = ["is_active = '1'"]
        params: list[str] = []
        if sales_person_id:
            clauses.append("id = ?")
            params.append(sales_person_id)
        if region:
            clauses.append("dept_name = ?")
            params.append(region)
        people = self.connection.execute("SELECT id, name, dept_name FROM v_sales_persons WHERE " + " AND ".join(clauses), params).fetchall()
        result: list[SalesPerformanceRow] = []
        for pid, name, dept in people:
            monthly_target = self.connection.execute("SELECT COALESCE(SUM(target_amount), 0) FROM crm.sales_targets WHERE owner_id = ? AND period = STRFTIME(CURRENT_DATE, '%Y-%m')", [pid]).fetchone()[0]
            monthly_signed = self.connection.execute("SELECT COALESCE(SUM(amount), 0) FROM v_sales_orders WHERE owner_id = ? AND order_date >= DATE_TRUNC('month', CURRENT_DATE)", [pid]).fetchone()[0]
            monthly_collected = self.connection.execute("SELECT COALESCE(SUM(received_amount), 0) FROM v_sales_orders WHERE owner_id = ? AND order_date >= DATE_TRUNC('month', CURRENT_DATE)", [pid]).fetchone()[0]
            ytd_target = self.connection.execute("SELECT COALESCE(SUM(target_amount), 0) FROM crm.sales_targets WHERE owner_id = ? AND period LIKE STRFTIME(CURRENT_DATE, '%Y') || '%'", [pid]).fetchone()[0]
            ytd_signed = self.connection.execute("SELECT COALESCE(SUM(amount), 0) FROM v_sales_orders WHERE owner_id = ? AND order_date >= DATE_TRUNC('year', CURRENT_DATE)", [pid]).fetchone()[0]
            ytd_collected = self.connection.execute("SELECT COALESCE(SUM(received_amount), 0) FROM v_sales_orders WHERE owner_id = ? AND order_date >= DATE_TRUNC('year', CURRENT_DATE)", [pid]).fetchone()[0]
            result.append(SalesPerformanceRow(pid, name, dept, float(monthly_target or 0), float(monthly_signed or 0), float(monthly_collected or 0), float(ytd_target or 0), float(ytd_signed or 0), float(ytd_collected or 0), SOURCE_CLASS, SOURCE_REF, RULE_VERSION))
        return tuple(result)

    def query_quote_competitiveness(self, opportunity_id: str | None = None) -> tuple[QuoteCompetitivenessRow, ...]:
        """报价竞争力视图：我方金额 + 竞品价（从备注解析）+ 成交标记。"""
        self.require_semantic_views()
        params: list[str] = []
        condition = ""
        if opportunity_id:
            condition = " WHERE id = ?"
            params.append(opportunity_id)
        rows = self.connection.execute(
            "SELECT id, customer_id, COALESCE(product_category, '通用'), amount, competitors FROM v_opportunities" + condition + " ORDER BY created_at DESC LIMIT 200", params,
        ).fetchall()
        result: list[QuoteCompetitivenessRow] = []
        for oid, cid, category, amount, competitors in rows:
            has_contract = self.connection.execute("SELECT COUNT(*) FROM v_contracts WHERE customer_id = ?", [cid]).fetchone()[0] > 0
            competitor_price = self._competitor_price(competitors)
            result.append(QuoteCompetitivenessRow(oid, cid, category, float(amount or 0), competitor_price, None, has_contract, SOURCE_CLASS, SOURCE_REF, RULE_VERSION))
        return tuple(result)

    def query_lead_quality(self, source: str | None = None) -> tuple[LeadQualityRow, ...]:
        """线索质量视图：按来源统计线索数与成交转化率。"""
        self.require_semantic_views()
        params: list[str] = []
        condition = ""
        if source:
            condition = " WHERE source = ?"
            params.append(source)
        rows = self.connection.execute(
            "SELECT source, COUNT(DISTINCT customer_id), 0 FROM v_leads" + condition + " GROUP BY source ORDER BY COUNT(DISTINCT customer_id) DESC LIMIT 50", params,
        ).fetchall()
        result: list[LeadQualityRow] = []
        for lead_source, total, _ in rows:
            converted = self.connection.execute("SELECT COUNT(DISTINCT l.customer_id) FROM v_leads l JOIN v_contracts c ON l.customer_id = c.customer_id WHERE l.source = ?", [lead_source]).fetchone()[0]
            result.append(LeadQualityRow(lead_source, int(total), int(converted), round(int(converted) / max(int(total), 1), 4), 0.0, 0.0, SOURCE_CLASS, SOURCE_REF, RULE_VERSION))
        return tuple(result)

    def compute_funnel_conversion(self, stage_from: str, stage_to: str) -> FunnelConversionResult:
        """漏斗转化计算：两个阶段商机数之比。"""
        self.require_semantic_views()
        total_from = self.connection.execute("SELECT COUNT(*) FROM v_opportunities WHERE stage = ?", [stage_from]).fetchone()[0]
        total_to = self.connection.execute("SELECT COUNT(*) FROM v_opportunities WHERE stage = ?", [stage_to]).fetchone()[0]
        return FunnelConversionResult(stage_from, stage_to, int(total_from), int(total_to), round(int(total_to) / max(int(total_from), 1), 4), SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    def score_customer_churn(self, customer_id: str) -> ChurnScoreResult:
        """客户流失评分：拜访缺失 + 无合同 + 长期未联系。"""
        self.require_semantic_views()
        contacts_90 = self.connection.execute("SELECT COUNT(*) FROM v_field_visits WHERE customer_id = ? AND visit_date >= CURRENT_DATE - INTERVAL 90 DAY", [customer_id]).fetchone()[0]
        visits_90 = self.connection.execute("SELECT COUNT(*) FROM v_field_visits WHERE customer_id = ? AND visit_type = '拜访' AND visit_date >= CURRENT_DATE - INTERVAL 90 DAY", [customer_id]).fetchone()[0]
        contracts_12 = self.connection.execute("SELECT COUNT(*) FROM v_contracts WHERE customer_id = ? AND sign_date >= CURRENT_DATE - INTERVAL 365 DAY", [customer_id]).fetchone()[0]
        last = self.connection.execute("SELECT MAX(visit_date) FROM v_field_visits WHERE customer_id = ?", [customer_id]).fetchone()[0]
        missing_visits = max(0, 3 - int(visits_90))
        score = 0.15 * min(missing_visits, 3) + (0.30 if int(contracts_12) == 0 else 0) + (0.30 if self._days_between(last) > 60 else 0) + (0.25 if int(contacts_90) == 0 else 0)
        score = round(min(score, 1.0), 2)
        level = "high" if score >= 0.6 else ("medium" if score >= 0.3 else "low")
        return ChurnScoreResult(customer_id, score, level, False, missing_visits, False, SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    def compute_quote_deviation(self, opportunity_id: str) -> QuoteDeviationResult:
        """报价偏离计算：我方报价 vs 竞品价。"""
        self.require_semantic_views()
        row = self.connection.execute("SELECT amount, competitors FROM v_opportunities WHERE id = ?", [opportunity_id]).fetchone()
        if not row:
            return QuoteDeviationResult(opportunity_id, 0, None, None, None, "MISSING", SOURCE_REF, RULE_VERSION)
        our_quote = float(row[0] or 0)
        competitor_price = self._competitor_price(row[1])
        deviation = round((our_quote - competitor_price) / competitor_price, 4) if competitor_price else None
        return QuoteDeviationResult(opportunity_id, our_quote, competitor_price, None, deviation, SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    def analyze_lead_source(self, source: str) -> LeadSourceAnalysisResult:
        """单个线索来源质量分析（真实 CRM 库）。"""
        rows = self.query_lead_quality(source)
        if not rows:
            return LeadSourceAnalysisResult(source, 0.0, 0.0, "poor", "该线索来源无数据记录，建议补充来源分类。", "MISSING", SOURCE_REF, RULE_VERSION)
        rate = rows[0].conversion_rate
        if rate >= 0.15:
            rating, recommendation = "excellent", "该来源转化率高，建议优先投放。"
        elif rate >= 0.08:
            rating, recommendation = "good", "该来源表现良好，可继续投入。"
        elif rate >= 0.04:
            rating, recommendation = "fair", "该来源转化一般，建议优化跟进策略。"
        else:
            rating, recommendation = "poor", "该来源转化率低，建议重新评估渠道价值。"
        return LeadSourceAnalysisResult(source, rate, 0.0, rating, recommendation, SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    @staticmethod
    def _competitor_price(value: object) -> float | None:
        """从竞品备注文本中提取首个数字作为竞品价；无数字返回 None。"""
        import re
        numbers = re.findall(r"\d+(?:\.\d+)?", str(value or ""))
        return float(numbers[0]) if numbers else None

    @staticmethod
    def _days_between(value: object) -> int:
        """计算日期字符串/日期对象距今天数；无效或缺失返回 999。"""
        if not value:
            return 999
        try:
            if isinstance(value, (date, datetime)):
                return (date.today() - value.date()).days if isinstance(value, datetime) else (date.today() - value).days
            return (date.today() - datetime.strptime(str(value)[:10], "%Y-%m-%d").date()).days
        except (TypeError, ValueError):
            return 999