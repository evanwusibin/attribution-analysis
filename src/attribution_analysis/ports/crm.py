"""CRM 只读数据端口（S9 · 售前场景 E1–E5）。

对齐 03_技术方案与架构.md 第七节：
- 6 个白名单语义视图，每视图绑定列白名单 + 行数上限 + 只读校验；
- 4 个售前计算工具，与售后 check_*/evaluate_* 命名区分；
- 全部返回携带 source_class/source_ref/rule_version，供 Evidence 回溯源。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


# ── 语义视图快照 ─────────────────────────────────────────────

@dataclass(frozen=True)
class OpportunityFunnelRow:
    """商机漏斗视图快照。"""
    opportunity_id: str
    customer_id: str
    sales_person_id: str
    stage: str
    amount: float
    days_in_stage: int
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class OpportunityFollowupRow:
    """商机跟进与拜访视图快照。"""
    opportunity_id: str
    customer_id: str
    followup_date: str
    followup_type: str  # 拜访/电话/线上
    content_summary: str | None
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class CustomerActivityRow:
    """客户活跃度视图快照。"""
    customer_id: str
    customer_name: str
    region: str
    contact_count_30d: int
    contact_count_90d: int
    visit_count_90d: int
    contract_count_12m: int
    last_contact_date: str | None
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class SalesPerformanceRow:
    """销售业绩视图快照。"""
    sales_person_id: str
    sales_person_name: str
    region: str
    monthly_target: float
    monthly_signed: float
    monthly_collected: float
    ytd_target: float
    ytd_signed: float
    ytd_collected: float
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class QuoteCompetitivenessRow:
    """报价竞争力视图快照。"""
    opportunity_id: str
    customer_id: str
    product_category: str
    our_quote: float
    competitor_price: float | None  # MISSING 时为 None
    industry_benchmark: float | None
    deal_closed: bool
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class LeadQualityRow:
    """线索质量视图快照。"""
    lead_source: str
    total_leads: int
    converted_customers: int
    conversion_rate: float
    avg_response_hours: float
    avg_first_deal_days: float
    source_class: str
    source_ref: str
    rule_version: str


# ── 计算工具输出 ─────────────────────────────────────────────

@dataclass(frozen=True)
class FunnelConversionResult:
    stage_from: str
    stage_to: str
    total_from: int
    total_to: int
    conversion_rate: float
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class ChurnScoreResult:
    customer_id: str
    churn_score: float       # 0–1, 越高越危险
    risk_level: str           # low / medium / high
    decline_trend: bool       # 跟进次数递减
    missing_field_visits: int  # 近 90 天缺失外勤次数
    competitor_exposure: bool
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class QuoteDeviationResult:
    opportunity_id: str
    our_quote: float
    deviation_from_competitor: float | None   # MISSING 时有竞争价但不可得
    deviation_from_benchmark: float | None
    deviation_percent: float | None
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class LeadSourceAnalysisResult:
    source: str
    conversion_rate: float
    avg_response_hours: float
    quality_rating: str       # poor / fair / good / excellent
    recommendation: str
    source_class: str
    source_ref: str
    rule_version: str


class CRMPort(Protocol):
    """CRM 只读数据的稳定端口。

    实现通过 DuckDB ATTACH 接⼊瑞能 CRM SQLite 库，仅暴露上述语义视图；
    不得执行任意 SQL、写入 CRM 或绕过列白名单。
    """

    # ── 6 个语义视图 ──

    def query_opportunity_funnel(
        self, region: str | None = None, stage: str | None = None
    ) -> tuple[OpportunityFunnelRow, ...]:
        """商机漏斗视图：opportunities 表的阶段、金额、停留时长。

        WHERE 条件仅限 region / stage 参数化过滤，禁止自由拼接。
        """

    def query_opportunity_followups(
        self, opportunity_id: str | None = None, customer_id: str | None = None,
    ) -> tuple[OpportunityFollowupRow, ...]:
        """商机跟进视图：field_visits + 跟进记录。"""

    def query_customer_activity(
        self, customer_id: str | None = None, region: str | None = None,
    ) -> tuple[CustomerActivityRow, ...]:
        """客户活跃度视图：近 30/90 天跟进、拜访、合同数。"""

    def query_sales_performance(
        self, sales_person_id: str | None = None, region: str | None = None,
    ) -> tuple[SalesPerformanceRow, ...]:
        """销售业绩视图：目标、签约、回款按销售/区域聚合。"""

    def query_quote_competitiveness(
        self, opportunity_id: str | None = None,
    ) -> tuple[QuoteCompetitivenessRow, ...]:
        """报价竞争力视图：报价与竞品偏离度。"""

    def query_lead_quality(
        self, source: str | None = None,
    ) -> tuple[LeadQualityRow, ...]:
        """线索质量视图：分来源转化率与跟进时效。"""

    # ── 4 个售前计算工具 ──

    def compute_funnel_conversion(
        self, stage_from: str, stage_to: str,
    ) -> FunnelConversionResult:
        """计算线索→客户→商机→合同漏斗转化率。"""

    def score_customer_churn(self, customer_id: str) -> ChurnScoreResult:
        """客户流失风险评分：跟进递减 + 外勤缺失 + 竞品接触。"""

    def compute_quote_deviation(self, opportunity_id: str) -> QuoteDeviationResult:
        """报价偏离度计算：我方报价 vs 竞品中标价 / 行业基准。"""

    def analyze_lead_source(self, source: str) -> LeadSourceAnalysisResult:
        """线索来源质量分析：转化率 + 跟进时效。"""