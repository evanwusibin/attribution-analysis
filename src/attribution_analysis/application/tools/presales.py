"""售前业务工具（S9 · E1–E5 场景）。
 
包裹 DemoCrmAdapter 的 4 个计算工具，全部阈值 MOCK。
对齐 03_技术方案与架构.md 第七节：compute_*/score_* 命名，与售后 check_*/evaluate_* 区分。
"""
from __future__ import annotations

from attribution_analysis.ports.crm import (
    CRMPort,
    ChurnScoreResult,
    FunnelConversionResult,
    LeadSourceAnalysisResult,
    QuoteDeviationResult,
)


class PresalesTools:
    """售前计算工具集：全部只读，输出带来源等级。"""

    def __init__(self, crm: CRMPort) -> None:
        """绑定 CRM 只读端口。"""
        self.crm = crm

    def compute_funnel_conversion(
        self, stage_from: str, stage_to: str,
    ) -> FunnelConversionResult:
        """漏斗转化率：从 stage_from 到 stage_to 的转化率（MOCK 统计值）。"""
        return self.crm.compute_funnel_conversion(stage_from, stage_to)

    def score_customer_churn(self, customer_id: str) -> ChurnScoreResult:
        """客户流失风险评分：跟进递减 + 外勤缺失 + 竞品接触（MOCK 阈值）。"""
        return self.crm.score_customer_churn(customer_id)

    def compute_quote_deviation(self, opportunity_id: str) -> QuoteDeviationResult:
        """报价偏离度：我方 vs 竞品（竞品价 MISSING 时降级）。"""
        return self.crm.compute_quote_deviation(opportunity_id)

    def analyze_lead_source(self, source: str) -> LeadSourceAnalysisResult:
        """线索来源质量分析：转化率 + 评级（MOCK 统计值）。"""
        return self.crm.analyze_lead_source(source)