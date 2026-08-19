"""MySQL 版 CRM 只读适配器：查询已迁移到 MySQL 的瑞能真实数据（crm_* 表）。

对齐 03_技术方案与架构.md 第七节：6 个白名单语义视图 + 4 个计算工具。

数据说明（已确认 2026-08-17）：
- 数据为脱敏真实数据：外键（owner_id/visitor_id/opportunity_id）被清空，姓名/部门名保留；
- customers.id + name 完整；opportunities.customer_id 有效（100/100）；
- field_visits.customer_name + visitor_name 完整（2643 条全部有姓名，1719 条有 customer_id）；
- sales_orders / contracts / sales_targets 仅保留 owner_dept（按部门聚合）；
- 客户成交判断使用 customers.first_deal_date 是否为空；拜访判断 visit_type 含「拜访」；
- 销售员 is_active = '在职'；销售目标 period 形如 '2026-01'（无当月时退化为统计全部目标）。
"""
from __future__ import annotations

from datetime import date

from attribution_analysis.infrastructure.database.duckdb import MySQLConnection
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

SOURCE_REF = "crm.ruien.mysql.v1"
SOURCE_CLASS = "FACT"
RULE_VERSION = "crm.view.v1"
# pymysql 的 mogrify 用 % 做占位符：SQL 文本中不得出现裸 %，一律放进参数值。
VISIT_PATTERN = "%拜访%"
TARGET_PREFIX = str(date.today().year) + "-%"


class MysqlCrmAdapter(CRMPort):
    """通过 MySQL 连接查询瑞能真实 CRM 数据，仅暴露白名单语义查询。"""

    def __init__(self, connection: MySQLConnection) -> None:
        """绑定 MySQL 连接（真实瑞能 CRM 数据）。"""
        self.connection = connection

    # ── 6 个白名单语义视图 ──────────────────────────────────

    def query_opportunity_funnel(
        self, region: str | None = None, stage: str | None = None,
    ) -> tuple[OpportunityFunnelRow, ...]:
        """商机漏斗视图：按区域/阶段过滤，返回商机及阶段停留天数。"""
        sql = (
            "SELECT o.id, o.customer_id, COALESCE(o.owner_dept, '未知'), o.stage, o.amount, o.created_at "
            "FROM crm_opportunities o WHERE 1=1"
        )
        params: list[str] = []
        if region:
            sql += " AND o.customer_id IN (SELECT id FROM crm_customers WHERE region = ?)"
            params.append(region)
        if stage:
            sql += " AND o.stage = ?"
            params.append(stage)
        sql += " ORDER BY o.created_at DESC LIMIT 500"
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(
            OpportunityFunnelRow(r[0], r[1], r[2], r[3], float(r[4] or 0), self._days_between(r[5]),
                                 SOURCE_CLASS, SOURCE_REF, RULE_VERSION)
            for r in rows
        )

    def query_opportunity_followups(
        self, opportunity_id: str | None = None, customer_id: str | None = None,
    ) -> tuple[OpportunityFollowupRow, ...]:
        """跟进记录视图：真实数据 opportunity_id 被清空时退化按客户匹配。"""
        sql = (
            "SELECT COALESCE(opportunity_id, ''), customer_id, visit_date, visit_type,"
            " SUBSTRING(COALESCE(content, ''), 1, 200) FROM crm_field_visits WHERE 1=1"
        )
        params: list[str] = []
        if opportunity_id:
            # 真实数据 opportunity_id 被清空，退化按客户匹配
            cid = self._customer_id_by_opportunity(opportunity_id)
            if cid:
                sql += " AND customer_id = ?"
                params.append(cid)
            else:
                return ()
        if customer_id:
            sql += " AND customer_id = ?"
            params.append(customer_id)
        sql += " ORDER BY visit_date DESC LIMIT 200"
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(
            OpportunityFollowupRow(r[0], r[1], r[2], r[3], r[4], SOURCE_CLASS, SOURCE_REF, RULE_VERSION)
            for r in rows
        )

    def _customer_id_by_opportunity(self, opportunity_id: str) -> str | None:
        """按商机 ID 反查客户 ID（外键被清空时的补偿查询）。"""
        row = self.connection.execute(
            "SELECT customer_id FROM crm_opportunities WHERE id = ?", [opportunity_id],
        ).fetchone()
        return row[0] if row and row[0] else None

    def query_customer_activity(
        self, customer_id: str | None = None, region: str | None = None,
    ) -> tuple[CustomerActivityRow, ...]:
        """客户活跃度视图：跟进/拜访/成交聚合，按客户或区域过滤。"""
        sql = "SELECT id, name, COALESCE(region, '未知') FROM crm_customers WHERE 1=1"
        params: list[str] = []
        if customer_id:
            sql += " AND id = ?"
            params.append(customer_id)
        if region:
            sql += " AND region = ?"
            params.append(region)
        sql += " LIMIT 500"
        rows = self.connection.execute(sql, params).fetchall()
        result: list[CustomerActivityRow] = []
        for r in rows:
            cid, cname, cregion = r[0], r[1], r[2]
            fv90 = self._count_visits(cid, 90)
            fv30 = self._count_visits(cid, 30)
            vis90 = self.connection.execute(
                "SELECT COUNT(*) FROM crm_field_visits WHERE customer_id = ? AND visit_type LIKE ? AND visit_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)",
                [cid, VISIT_PATTERN],
            ).fetchone()[0]
            deal = self.connection.execute(
                "SELECT deal_status FROM crm_customers WHERE id = ?", [cid],
            ).fetchone()[0]
            ct12 = 1 if deal and deal not in ("未成交", None) else 0
            last = self.connection.execute(
                "SELECT MAX(visit_date) FROM crm_field_visits WHERE customer_id = ?", [cid],
            ).fetchone()[0]
            result.append(CustomerActivityRow(cid, cname, cregion, int(fv30), int(fv90), int(vis90), int(ct12),
                                              str(last) if last else None,
                                              SOURCE_CLASS, SOURCE_REF, RULE_VERSION))
        return tuple(result)

    def _count_visits(self, customer_id: str, days: int) -> int:
        """统计客户近 N 天拜访次数（内部工具）。"""
        row = self.connection.execute(
            "SELECT COUNT(*) FROM crm_field_visits WHERE customer_id = ? AND visit_date >= DATE_SUB(CURDATE(), INTERVAL ? DAY)",
            [customer_id, days],
        ).fetchone()
        return int(row[0] or 0)

    def query_sales_performance(
        self, sales_person_id: str | None = None, region: str | None = None,
    ) -> tuple[SalesPerformanceRow, ...]:
        """真实数据外键被清空：按部门（dept_name）聚合业绩。"""
        sql = "SELECT sp.id, sp.name, COALESCE(sp.dept_name, '未知'), sp.dept_name FROM crm_sales_persons sp WHERE sp.is_active = '在职'"
        params: list[str] = []
        if sales_person_id:
            sql += " AND sp.id = ?"
            params.append(sales_person_id)
        if region:
            sql += " AND sp.dept_name = ?"
            params.append(region)
        rows = self.connection.execute(sql, params).fetchall()
        result: list[SalesPerformanceRow] = []
        for r in rows:
            pid, pname, dept, raw_dept = r[0], r[1], r[2], r[3]
            # 脱敏数据时间维度错位（订单 2025 / 目标 2026）：业绩统计退化为全部数据总量的部门对比，
            # 时间过滤仍然保留（防止未来数据接入时口径漂移），但当前有效口径是 yt/ys/yc。
            mt = self._sum_where("crm_sales_targets", "target_amount",
                                 "owner_dept = %s AND period LIKE ?", raw_dept, TARGET_PREFIX)
            ms = self._sum_where("crm_sales_orders", "amount",
                                 "owner_dept = %s AND created_at >= ?", raw_dept, "2020-01-01 00:00:00")
            mc = self._sum_where("crm_sales_orders", "received_amount",
                                 "owner_dept = %s AND created_at >= ?", raw_dept, "2020-01-01 00:00:00")
            yt = self._sum_where("crm_sales_targets", "target_amount",
                                 "owner_dept = %s AND period LIKE ?", raw_dept, TARGET_PREFIX)
            ys = self._sum_where("crm_sales_orders", "amount",
                                 "owner_dept = %s AND created_at >= ?", raw_dept, "2020-01-01 00:00:00")
            yc = self._sum_where("crm_sales_orders", "received_amount",
                                 "owner_dept = %s AND created_at >= ?", raw_dept, "2020-01-01 00:00:00")
            result.append(SalesPerformanceRow(pid, pname, dept, mt, ms, mc, yt, ys, yc,
                                              SOURCE_CLASS, SOURCE_REF, RULE_VERSION))
        return tuple(result)

    def _sum_where(self, table: str, field: str, where: str, *params: str) -> float:
        """按条件对指定表字段求和（内部工具，表名/字段来自白名单）。"""
        row = self.connection.execute(
            f"SELECT COALESCE(SUM({field}), 0) FROM {table} WHERE {where}", list(params),
        ).fetchone()
        return float(row[0] or 0)

    def query_quote_competitiveness(
        self, opportunity_id: str | None = None,
    ) -> tuple[QuoteCompetitivenessRow, ...]:
        """报价竞争力视图：我方金额 + 竞品价（从备注解析）+ 成交标记。"""
        sql = (
            "SELECT o.id, o.customer_id, COALESCE(o.product_category, '通用'), o.amount, o.competitors "
            "FROM crm_opportunities o WHERE 1=1"
        )
        params: list[str] = []
        if opportunity_id:
            sql += " AND o.id = ?"
            params.append(opportunity_id)
        sql += " ORDER BY o.created_at DESC LIMIT 200"
        rows = self.connection.execute(sql, params).fetchall()
        result: list[QuoteCompetitivenessRow] = []
        for r in rows:
            oid, cid, cat, amount, competitors = r[0], r[1], r[2], r[3], r[4]
            deal = self.connection.execute(
                "SELECT deal_status FROM crm_customers WHERE id = ?", [cid],
            ).fetchone()[0]
            has_contract = bool(deal and deal != "未成交")
            comp_price: float | None = None
            if competitors:
                import re
                nums = re.findall(r"\d+(?:\.\d+)?", str(competitors))
                if nums:
                    try:
                        comp_price = float(nums[0])
                    except ValueError:
                        pass
            result.append(QuoteCompetitivenessRow(oid, cid, cat, float(amount or 0), comp_price, None, has_contract,
                                                  SOURCE_CLASS, SOURCE_REF, RULE_VERSION))
        return tuple(result)

    def query_lead_quality(
        self, source: str | None = None,
    ) -> tuple[LeadQualityRow, ...]:
        """线索质量视图：按来源统计线索数与成交转化率。"""
        sql = (
            "SELECT COALESCE(c.source, '未知'), COUNT(DISTINCT c.id), "
            "SUM(CASE WHEN c.deal_status IN ('已成交','多次成交') THEN 1 ELSE 0 END) "
            "FROM crm_customers c "
            "WHERE c.source IS NOT NULL AND c.source != '' AND c.source != 'NULL'"
        )
        params: list[str] = []
        if source:
            sql += " AND c.source = ?"
            params.append(source)
        sql += " GROUP BY c.source ORDER BY COUNT(DISTINCT c.id) DESC LIMIT 50"
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(
            LeadQualityRow(
                lead_source=r[0], total_leads=int(r[1]), converted_customers=int(r[2]),
                conversion_rate=round(int(r[2]) / max(int(r[1]), 1), 4),
                avg_response_hours=0.0, avg_first_deal_days=0.0,
                source_class=SOURCE_CLASS, source_ref=SOURCE_REF, rule_version=RULE_VERSION,
            )
            for r in rows
        )

    # ── 4 个售前计算工具 ────────────────────────────────────

    def compute_funnel_conversion(self, stage_from: str, stage_to: str) -> FunnelConversionResult:
        """漏斗转化计算：两个阶段商机数之比（白名单阶段值）。"""
        total_from = self.connection.execute(
            "SELECT COUNT(*) FROM crm_opportunities WHERE stage = ?", [stage_from],
        ).fetchone()[0]
        total_to = self.connection.execute(
            "SELECT COUNT(*) FROM crm_opportunities WHERE stage = ?", [stage_to],
        ).fetchone()[0]
        rate = round(int(total_to) / max(int(total_from), 1), 4)
        return FunnelConversionResult(stage_from, stage_to, int(total_from), int(total_to), rate,
                                      SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    def score_customer_churn(self, customer_id: str) -> ChurnScoreResult:
        """客户流失评分：跟进递减 + 外勤缺失 + 无成交 + 长期未联系。"""
        deal_row = self.connection.execute(
            "SELECT deal_status FROM crm_customers WHERE id = ?", [customer_id],
        ).fetchone()
        if not deal_row:
            return ChurnScoreResult(customer_id, 1.0, "high", False, 3, False, "MISSING", SOURCE_REF, RULE_VERSION)
        contacts_90d = self._count_visits(customer_id, 90)
        visits_90d = self.connection.execute(
            "SELECT COUNT(*) FROM crm_field_visits WHERE customer_id = ? AND visit_type LIKE ? AND visit_date >= DATE_SUB(CURDATE(), INTERVAL 90 DAY)",
            [customer_id, VISIT_PATTERN],
        ).fetchone()[0]
        contracts_12m = 1 if deal_row[0] and deal_row[0] != "未成交" else 0
        last = self.connection.execute(
            "SELECT MAX(visit_date) FROM crm_field_visits WHERE customer_id = ?", [customer_id],
        ).fetchone()[0]

        missing_visits = max(0, 3 - int(visits_90d))
        score = 0.0
        if missing_visits > 0:
            score += 0.15 * min(missing_visits, 3)
        if int(contracts_12m) == 0:
            score += 0.30
        last_days = self._days_between(str(last)) if last else 999
        if last_days > 60:
            score += 0.30
        if int(contacts_90d) == 0:
            score += 0.25
        score = round(min(score, 1.0), 2)
        level = "high" if score >= 0.6 else ("medium" if score >= 0.3 else "low")
        return ChurnScoreResult(customer_id, score, level, False, missing_visits,
                                False, SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    def compute_quote_deviation(self, opportunity_id: str) -> QuoteDeviationResult:
        """报价偏离计算：我方报价 vs 竞品价，返回偏差百分比。"""
        row = self.connection.execute(
            "SELECT amount, competitors FROM crm_opportunities WHERE id = ?", [opportunity_id],
        ).fetchone()
        if not row:
            return QuoteDeviationResult(opportunity_id, 0, None, None, None, "MISSING", SOURCE_REF, RULE_VERSION)
        our_quote = float(row[0] or 0)
        comp_price: float | None = None
        if row[1]:
            import re
            nums = re.findall(r"\d+(?:\.\d+)?", str(row[1]))
            if nums:
                try:
                    comp_price = float(nums[0])
                except ValueError:
                    pass
        if comp_price is not None and comp_price > 0:
            dev_pct = round((our_quote - comp_price) / comp_price, 4)
            return QuoteDeviationResult(opportunity_id, our_quote, comp_price, None, dev_pct,
                                        SOURCE_CLASS, SOURCE_REF, RULE_VERSION)
        return QuoteDeviationResult(opportunity_id, our_quote, None, None, None, SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    def analyze_lead_source(self, source: str) -> LeadSourceAnalysisResult:
        """单个线索来源质量分析。"""
        row = self.connection.execute(
            "SELECT c.source, COUNT(DISTINCT c.id), "
            "SUM(CASE WHEN c.deal_status IN ('已成交','多次成交') THEN 1 ELSE 0 END) "
            "FROM crm_customers c WHERE c.source = ? GROUP BY c.source", [source],
        ).fetchone()
        if not row or int(row[1]) == 0:
            return LeadSourceAnalysisResult(source, 0.0, 0.0, "poor", "该线索来源无数据记录，建议补充来源分类。",
                                            "MISSING", SOURCE_REF, RULE_VERSION)
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
        return LeadSourceAnalysisResult(source, rate, 0.0, rating, rec, SOURCE_CLASS, SOURCE_REF, RULE_VERSION)

    @staticmethod
    def _days_between(date_str: str | None) -> int:
        """计算日期字符串距今天数；无效或缺失返回 999。"""
        from datetime import datetime
        if not date_str:
            return 999
        try:
            d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
            return (date.today() - d).days
        except ValueError:
            return 999
