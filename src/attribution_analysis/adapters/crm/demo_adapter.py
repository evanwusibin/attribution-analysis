"""售前模拟适配器：查询 DuckDB PRE_SALES 表，返回 MOCK 证据。

对齐 CrmReadonlyAdapter 的 6 视图 + 4 工具契约，但数据源为固定 seed 模拟库。
所有计算使用 REFERENCE_DATE（2024-08-17）替代 `julianday('now')`，保证可复现。

本模块是从 adapters/crm/demo.py 拆分出的「模拟库」实现（MOCK 证据）；
真实库实现见 adapters/crm/readonly.py。
"""
from __future__ import annotations

from datetime import date, datetime

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

# S9 模拟数据常量
MOCK_SOURCE_REF = "demo.duckdb.presales.v1"
MOCK_SOURCE_CLASS = "MOCK"
MOCK_RULE_VERSION = "presales.demo.v1"
# 参考日期：所有固定日期计算基于此（seed=42 可复现）
REFERENCE_DATE = date(2024, 8, 17)


class DemoCrmAdapter(CRMPort):
    """售前模拟适配器：查询 DuckDB PRE_SALES 表，返回 MOCK 证据。

    对齐 CrmReadonlyAdapter 的 6 视图 + 4 工具契约，但数据源为固定 seed 模拟库。
    所有计算使用 REFERENCE_DATE（2024-08-17）替代 `julianday('now')`，保证可复现。
    """

    def __init__(self, connection: DuckDBPyConnection) -> None:
        """绑定模拟库连接并固定参考日期（可复现）。"""
        self.connection = connection
        self._ref = REFERENCE_DATE

    @staticmethod
    def _days_between(start: str, end: date | None = None) -> int:
        """计算开始日期到参考日期的天数差。"""
        d = datetime.strptime(start[:10], "%Y-%m-%d").date()
        return (end or REFERENCE_DATE - d).days

    def _r(self, *extra: object) -> tuple[object, ...]:
        """附加 MOCK 来源标记（source_class/source_ref/rule_version）。"""
        return extra + (MOCK_SOURCE_CLASS, MOCK_SOURCE_REF, MOCK_RULE_VERSION)

    # ── 6 个白名单语义视图 ──────────────────────────────────

    def query_opportunity_funnel(
        self, region: str | None = None, stage: str | None = None,
    ) -> tuple[OpportunityFunnelRow, ...]:
        """商机漏斗视图（模拟库）：按区域/阶段过滤返回商机及停留天数。"""
        sql = "SELECT id, customer_id, owner_id, stage, amount, created_at FROM pre_opportunities WHERE 1=1"
        params: list[str] = []
        if region:
            sql += " AND customer_id IN (SELECT id FROM pre_customers WHERE region = ?)"
            params.append(region)
        if stage:
            sql += " AND stage = ?"
            params.append(stage)
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(
            OpportunityFunnelRow(row[0], row[1], row[2], row[3], float(row[4]),
                                 self._days_between(row[5]), *self._r())
            for row in rows
        )

    def query_opportunity_followups(
        self, opportunity_id: str | None = None, customer_id: str | None = None,
    ) -> tuple[OpportunityFollowupRow, ...]:
        """跟进记录视图（模拟库）：按商机或客户过滤拜访记录。"""
        sql = "SELECT opportunity_id, customer_id, visit_date, visit_type, content FROM pre_field_visits WHERE 1=1"
        params: list[str] = []
        if opportunity_id:
            sql += " AND opportunity_id = ?"
            params.append(opportunity_id)
        if customer_id:
            sql += " AND customer_id = ?"
            params.append(customer_id)
        sql += " ORDER BY visit_date DESC"
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(
            OpportunityFollowupRow(row[0], row[1], row[2], row[3], row[4], *self._r())
            for row in rows
        )

    def query_customer_activity(
        self, customer_id: str | None = None, region: str | None = None,
    ) -> tuple[CustomerActivityRow, ...]:
        """客户活跃度视图（模拟库）：跟进/拜访/合同聚合。"""
        sql = "SELECT id, name, region FROM pre_customers WHERE 1=1"
        params: list[str] = []
        if customer_id:
            sql += " AND id = ?"
            params.append(customer_id)
        if region:
            sql += " AND region = ?"
            params.append(region)
        rows = self.connection.execute(sql, params).fetchall()
        result: list[CustomerActivityRow] = []
        for row in rows:
            cid, cname, cregion = row[0], row[1], row[2]
            # 近 30 天跟进
            fv30 = self.connection.execute(
                "SELECT COUNT(*) FROM pre_field_visits WHERE customer_id = ? AND visit_date >= ?",
                [cid, "2024-07-18"],
            ).fetchone()[0]
            # 近 90 天跟进
            fv90 = self.connection.execute(
                "SELECT COUNT(*) FROM pre_field_visits WHERE customer_id = ? AND visit_date >= ?",
                [cid, "2024-05-19"],
            ).fetchone()[0]
            # 近 90 天拜访
            vis90 = self.connection.execute(
                "SELECT COUNT(*) FROM pre_field_visits WHERE customer_id = ? AND visit_date >= ? AND visit_type = '拜访'",
                [cid, "2024-05-19"],
            ).fetchone()[0]
            # 近 12 月合同数
            ct12 = self.connection.execute(
                "SELECT COUNT(*) FROM pre_contracts WHERE customer_id = ? AND sign_date >= ?",
                [cid, "2023-08-17"],
            ).fetchone()[0]
            # 最后联系日期
            last = self.connection.execute(
                "SELECT MAX(visit_date) FROM pre_field_visits WHERE customer_id = ?",
                [cid],
            ).fetchone()[0]
            result.append(CustomerActivityRow(cid, cname, cregion, fv30, fv90, vis90, ct12, last, *self._r()))
        return tuple(result)

    def query_sales_performance(
        self, sales_person_id: str | None = None, region: str | None = None,
    ) -> tuple[SalesPerformanceRow, ...]:
        """业绩视图（模拟库）：月/年度目标-签约-回款聚合。"""
        sql = "SELECT sp.id, sp.name, sp.dept_name FROM pre_sales_persons sp WHERE sp.is_active = '1'"
        params: list[str] = []
        if sales_person_id:
            sql += " AND sp.id = ?"
            params.append(sales_person_id)
        if region:
            sql += " AND sp.dept_name = ?"
            params.append(region)
        rows = self.connection.execute(sql, params).fetchall()
        result: list[SalesPerformanceRow] = []
        for row in rows:
            pid, pname, dept = row[0], row[1], row[2]
            # 月目标
            mt = self.connection.execute(
                "SELECT COALESCE(SUM(target_amount), 0) FROM pre_sales_targets WHERE owner_id = ? AND period = '2024-08'",
                [pid],
            ).fetchone()[0]
            # 月签约
            ms = self.connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM pre_sales_orders WHERE owner_id = ? AND order_date >= '2024-08-01' AND order_date < '2024-09-01'",
                [pid],
            ).fetchone()[0]
            # 月回款
            mc = self.connection.execute(
                "SELECT COALESCE(SUM(received_amount), 0) FROM pre_sales_orders WHERE owner_id = ? AND order_date >= '2024-08-01' AND order_date < '2024-09-01'",
                [pid],
            ).fetchone()[0]
            # 年度目标
            yt = self.connection.execute(
                "SELECT COALESCE(SUM(target_amount), 0) FROM pre_sales_targets WHERE owner_id = ? AND period = '2024-YTD'",
                [pid],
            ).fetchone()[0]
            # 年度签约
            ys = self.connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM pre_sales_orders WHERE owner_id = ? AND order_date >= '2024-01-01'",
                [pid],
            ).fetchone()[0]
            # 年度回款
            yc = self.connection.execute(
                "SELECT COALESCE(SUM(received_amount), 0) FROM pre_sales_orders WHERE owner_id = ? AND order_date >= '2024-01-01'",
                [pid],
            ).fetchone()[0]
            result.append(SalesPerformanceRow(pid, pname, dept, float(mt), float(ms), float(mc),
                                              float(yt), float(ys), float(yc), *self._r()))
        return tuple(result)

    def query_quote_competitiveness(
        self, opportunity_id: str | None = None,
    ) -> tuple[QuoteCompetitivenessRow, ...]:
        """报价竞争力视图（模拟库）：我方金额 + 竞品价 + 成交标记。"""
        sql = "SELECT o.id, o.customer_id, COALESCE(o.product_category, '通用'), o.amount, o.competitors FROM pre_opportunities o WHERE 1=1"
        params: list[str] = []
        if opportunity_id:
            sql += " AND o.id = ?"
            params.append(opportunity_id)
        rows = self.connection.execute(sql, params).fetchall()
        result: list[QuoteCompetitivenessRow] = []
        for row in rows:
            oid, cid, cat, amount, competitors = row[0], row[1], row[2], row[3], row[4]
            # 检查是否有合同（成交标志）
            has_contract = self.connection.execute(
                "SELECT COUNT(*) FROM pre_contracts WHERE customer_id = ?",
                [cid],
            ).fetchone()[0] > 0
            # 从 competitors 文本中解析竞品价格（MISSING 时返回 None）
            comp_price: float | None = None
            if competitors and "报价" in competitors:
                import re
                m = re.search(r'(\d+)', competitors.replace(",", ""))
                if m:
                    comp_price = float(m.group(1))
            result.append(QuoteCompetitivenessRow(oid, cid, cat, float(amount), comp_price, None, has_contract,
                                                  *self._r()))
        return tuple(result)

    def query_lead_quality(
        self, source: str | None = None,
    ) -> tuple[LeadQualityRow, ...]:
        """线索质量视图（模拟库）：按来源统计线索数与成交转化率。"""
        sql = "SELECT c.source, COUNT(DISTINCT c.id), COUNT(DISTINCT ct.id) FROM pre_customers c LEFT JOIN pre_contracts ct ON c.id = ct.customer_id WHERE c.source IS NOT NULL AND c.source != ''"
        params: list[str] = []
        if source:
            sql += " AND c.source = ?"
            params.append(source)
        sql += " GROUP BY c.source"
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(
            LeadQualityRow(
                lead_source=row[0],
                total_leads=int(row[1]),
                converted_customers=int(row[2]),
                conversion_rate=round(int(row[2]) / max(int(row[1]), 1), 4),
                avg_response_hours=0.0,
                avg_first_deal_days=0.0,
                source_class=MOCK_SOURCE_CLASS,
                source_ref=MOCK_SOURCE_REF,
                rule_version=MOCK_RULE_VERSION,
            )
            for row in rows
        )

    # ── 4 个售前计算工具 ────────────────────────────────────

    def compute_funnel_conversion(self, stage_from: str, stage_to: str) -> FunnelConversionResult:
        """漏斗转化计算（模拟库）：两个阶段商机数之比。"""
        total_from = self.connection.execute(
            "SELECT COUNT(*) FROM pre_opportunities WHERE stage = ?", [stage_from],
        ).fetchone()[0]
        total_to = self.connection.execute(
            "SELECT COUNT(*) FROM pre_opportunities WHERE stage = ?", [stage_to],
        ).fetchone()[0]
        rate = round(total_to / max(total_from, 1), 4)
        return FunnelConversionResult(stage_from, stage_to, total_from, total_to, rate, *self._r())

    def score_customer_churn(self, customer_id: str) -> ChurnScoreResult:
        """客户流失评分（模拟库）：递减趋势 + 拜访缺失 + 无合同 + 长期未联系。"""
        contacts_90d = self.connection.execute(
            "SELECT COUNT(*) FROM pre_field_visits WHERE customer_id = ? AND visit_date >= '2024-05-19'",
            [customer_id],
        ).fetchone()[0]
        visits_90d = self.connection.execute(
            "SELECT COUNT(*) FROM pre_field_visits WHERE customer_id = ? AND visit_date >= '2024-05-19' AND visit_type = '拜访'",
            [customer_id],
        ).fetchone()[0]
        contacts_prev = self.connection.execute(
            "SELECT COUNT(*) FROM pre_field_visits WHERE customer_id = ? AND visit_date >= '2024-02-18' AND visit_date < '2024-05-19'",
            [customer_id],
        ).fetchone()[0]
        contracts_12m = self.connection.execute(
            "SELECT COUNT(*) FROM pre_contracts WHERE customer_id = ? AND sign_date >= '2023-08-17'",
            [customer_id],
        ).fetchone()[0]
        last = self.connection.execute(
            "SELECT MAX(visit_date) FROM pre_field_visits WHERE customer_id = ?",
            [customer_id],
        ).fetchone()[0]

        decline_trend = bool(contacts_90d < contacts_prev if contacts_prev > 0 else False)
        missing_visits = max(0, 3 - visits_90d)
        score = 0.0
        if decline_trend:
            score += 0.25
        if missing_visits > 0:
            score += 0.15 * min(missing_visits, 3)
        if contracts_12m == 0:
            score += 0.30
        last_days = self._days_between(last) if last else 999
        if last_days > 60:
            score += 0.30
        score = round(min(score, 1.0), 2)
        level = "high" if score >= 0.6 else ("medium" if score >= 0.3 else "low")
        return ChurnScoreResult(customer_id, score, level, decline_trend, missing_visits,
                                False, *self._r())

    def compute_quote_deviation(self, opportunity_id: str) -> QuoteDeviationResult:
        """报价偏离计算（模拟库）：我方报价 vs 竞品价。"""
        row = self.connection.execute(
            "SELECT amount, competitors FROM pre_opportunities WHERE id = ?", [opportunity_id],
        ).fetchone()
        if not row:
            return QuoteDeviationResult(opportunity_id, 0, None, None, None, "MISSING", MOCK_SOURCE_REF, MOCK_RULE_VERSION)
        our_quote = float(row[0])
        import re
        comp_price: float | None = None
        if row[1] and "报价" in row[1]:
            m = re.search(r'(\d+)', row[1].replace(",", ""))
            if m:
                comp_price = float(m.group(1))
        if comp_price is not None:
            dev_pct = round((our_quote - comp_price) / comp_price, 4)
            return QuoteDeviationResult(opportunity_id, our_quote, comp_price, None, dev_pct, *self._r())
        return QuoteDeviationResult(opportunity_id, our_quote, None, None, None, *self._r())

    def analyze_lead_source(self, source: str) -> LeadSourceAnalysisResult:
        """单个线索来源质量分析（模拟库）。"""
        row = self.connection.execute(
            "SELECT c.source, COUNT(DISTINCT c.id), COUNT(DISTINCT ct.id)"
            " FROM pre_customers c LEFT JOIN pre_contracts ct ON c.id = ct.customer_id"
            " WHERE c.source = ? GROUP BY c.source",
            [source],
        ).fetchone()
        if not row or int(row[1]) == 0:
            return LeadSourceAnalysisResult(source, 0.0, 0.0, "poor", "该线索来源无数据记录，建议补充来源分类。",
                                            "MISSING", MOCK_SOURCE_REF, MOCK_RULE_VERSION)
        total = int(row[1])
        converted = int(row[2])
        rate = round(converted / max(total, 1), 4)
        if rate >= 0.15:
            rating, rec = "excellent", "该来源转化率高，建议优先投放。"
        elif rate >= 0.08:
            rating, rec = "good", "该来源表现良好，可继续投入。"
        elif rate >= 0.04:
            rating, rec = "fair", "该来源转化一般，建议优化跟进策略。"
        else:
            rating, rec = "poor", "该来源转化率低，建议重新评估渠道价值。"
        return LeadSourceAnalysisResult(source, rate, 0.0, rating, rec, *self._r())