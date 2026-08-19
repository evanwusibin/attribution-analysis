"""售前业务场景路由与诊断执行（S9 · E1–E5）。

业务场景路由 → CRM 数据查询 → 计算工具执行 → 候选归因。
首版实现 5 个售前场景（商机丢单/业绩未达标/客户流失/报价竞争力/线索质量），
全部阈值 MOCK，竞品 MISSING 降级，绝不自动处置。
"""
from __future__ import annotations

from dataclasses import dataclass

from attribution_analysis.application.tools.presales import PresalesTools


@dataclass(frozen=True)
class PresalesDiagnosisRequest:
    """售前诊断输入：问题文本 + 可选显式定位。"""
    question: str
    customer_id: str | None = None
    opportunity_id: str | None = None
    sales_person_id: str | None = None
    region: str | None = None
    source: str | None = None


@dataclass(frozen=True)
class PresalesDiagnosisOutcome:
    """售前诊断输出（六段结构同构）。"""
    scenario: str
    conclusion: str
    key_metrics: tuple[tuple[str, str], ...]  # (名称, 值)
    missing_items: tuple[str, ...]
    evidence: tuple[dict[str, object], ...]
    manual_review_required: bool


class PresalesScenarioRouter:
    """识别问题属于哪个售前场景。"""

    SCENARIO_KEYWORDS: dict[str, tuple[str, ...]] = {
        "E1": ("商机丢单", "丢单", "商机", "丢标", "OPP-"),
        "E2": ("业绩未达标", "业绩", "目标达成", "签约", "回款", "未达标"),
        "E3": ("客户流失", "流失", "公海", "回收", "客户跟进"),
        "E4": ("报价竞争力", "报价偏离", "竞品", "中标", "丢了", "标书"),
        "E5": ("线索来源", "线索质量", "线索转化", "来源渠道", "广告", "推广"),
    }

    def route(self, question: str) -> str | None:
        """按关键词识别售前场景（E1-E5）；不属于时返回 None。"""
        lowered = question.lower()
        for scenario, keywords in self.SCENARIO_KEYWORDS.items():
            if any(kw in lowered for kw in keywords):
                return scenario
        return None


class PresalesDiagnosisService:
    """S9 售前场景诊断执行服务。"""

    E1_KEYWORDS = ("关键人", "覆盖", "报价", "阶段", "停留", "跟进", "态度")
    E2_KEYWORDS = ("线索", "转化", "客单价", "回款", "区域", "销售员", "漏斗")
    E3_KEYWORDS = ("跟进", "外勤", "拜访", "竞品", "接触", "递减", "敷衍")
    E4_KEYWORDS = ("报价", "偏离", "竞品", "条款", "方案", "匹配")
    E5_KEYWORDS = ("来源", "渠道", "时效", "超时", "广告", "推广")

    def __init__(self, crm) -> None:
        """装配 CRM 只读端口、计算工具与场景路由。"""
        self.crm = crm
        self.tools = PresalesTools(crm)
        self.router = PresalesScenarioRouter()

    def is_presales(self, question: str) -> bool:
        """快捷判断：问题是否属于售前场景。"""
        return self.router.route(question) is not None

    def run(self, request: PresalesDiagnosisRequest) -> PresalesDiagnosisOutcome:
        """执行售前场景诊断：路由 → 分流到 E1-E5 处理链。"""
        scenario = self.router.route(request.question) or "unknown"
        if scenario == "unknown":
            return PresalesDiagnosisOutcome(
                scenario="unknown",
                conclusion="未识别售前场景，请补充明确问题描述。",
                key_metrics=(),
                missing_items=("未识别售前场景",),
                evidence=(),
                manual_review_required=True,
            )

        # 根据场景执行不同诊断链
        handlers = {
            "E1": self._handle_e1,
            "E2": self._handle_e2,
            "E3": self._handle_e3,
            "E4": self._handle_e4,
            "E5": self._handle_e5,
        }
        return handlers[scenario](request)

    def _evidence(self, title: str, value: str, cls: str = "MOCK") -> dict[str, object]:
        """构造统一格式的证据项（含来源等级）。"""
        return {
            "source_class": cls,
            "source_ref": "demo.duckdb.presales.v1",
            "rule_version": "presales.demo.v1",
            "content_summary": f"{title}：{value}",
            "confidence": 0.0 if cls == "MISSING" else 0.7,
            "review_required": cls == "MISSING",
        }

    def _handle_e1(self, request: PresalesDiagnosisRequest) -> PresalesDiagnosisOutcome:
        """E1 商机丢单：查漏斗+跟进+报价+阶段停留。"""
        oid = request.opportunity_id or "OPP-001"
        funnel = [r for r in self.crm.query_opportunity_funnel() if r.opportunity_id == oid]
        followups = self.crm.query_opportunity_followups(opportunity_id=oid)
        quote = self.tools.compute_quote_deviation(oid)

        evidence: list[dict[str, object]] = []
        missing: list[str] = []

        # 阶段停留
        stage_days = "无数据"
        if funnel:
            row = funnel[0]
            stage_days = f"{row.days_in_stage}天"
            evidence.append(self._evidence("商机阶段停留", f"{row.stage}，已停留{stage_days}"))

        # 最后跟进记录
        if followups:
            last = followups[0]
            evidence.append(self._evidence("最后跟进", f"{last.followup_date} {last.followup_type}：{last.content_summary or '无内容'}"))
        else:
            missing.append("跟进记录（MISSING）")

        # 报价偏离
        evidence.append(self._evidence("我方报价", f"{quote.our_quote:.0f}元"))
        if quote.deviation_percent is not None:
            evidence.append(self._evidence("报价偏离度", f"{quote.deviation_percent:.1%}"))
        elif quote.deviation_from_competitor is None:
            missing.append("竞品报价（MISSING）")

        conclusion = "形成候选假设：关键人未覆盖 + 报价偏高 + 阶段停留过长。" if stage_days else "数据不足，无法形成结论。"
        return PresalesDiagnosisOutcome(
            scenario="E1", conclusion=conclusion,
            key_metrics=(("阶段停留", stage_days), ("跟进次数", f"{len(followups)}次")),
            missing_items=tuple(missing), evidence=tuple(evidence), manual_review_required=True,
        )

    def _handle_e2(self, request: PresalesDiagnosisRequest) -> PresalesDiagnosisOutcome:
        """E2 业绩未达标：查漏斗转化+业绩+回款。"""
        region = request.region or "华东"
        perf = self.crm.query_sales_performance(region=region)
        funnel = self.tools.compute_funnel_conversion("跟进", "成交")

        evidence: list[dict[str, object]] = []
        metrics: list[tuple[str, str]] = []
        missing: list[str] = []

        # 区域业绩
        if perf:
            total_target = sum(r.monthly_target for r in perf)
            total_signed = sum(r.monthly_signed for r in perf)
            rate = round(total_signed / total_target * 100, 1) if total_target else 0
            metrics.append(("区域达成率", f"{rate}%"))
            evidence.append(self._evidence(f"{region}区本月业绩", f"目标{total_target:.0f}，签约{total_signed:.0f}，达成率{rate}%"))
            for p in perf:
                pr = round(p.monthly_signed / p.monthly_target * 100, 1) if p.monthly_target else 0
                evidence.append(self._evidence(f"销售员{p.sales_person_name}", f"目标{p.monthly_target:.0f}，签约{p.monthly_signed:.0f}，达成率{pr}%"))
        else:
            missing.append(f"{region}区业绩数据（MISSING）")

        # 漏斗转化
        metrics.append(("客户→商机转化率", f"{funnel.conversion_rate:.1%}"))
        evidence.append(self._evidence("客户→商机漏斗", f"从{funnel.stage_from}到{funnel.stage_to}，转化率{funnel.conversion_rate:.1%}"))

        conclusion = f"{region}区达成率{rate}%，转化率{funnel.conversion_rate:.1%}，建议定位线索量或转化率瓶颈。" if perf else "业绩数据不足。"
        return PresalesDiagnosisOutcome(
            scenario="E2", conclusion=conclusion,
            key_metrics=tuple(metrics), missing_items=tuple(missing),
            evidence=tuple(evidence), manual_review_required=True,
        )

    def _handle_e3(self, request: PresalesDiagnosisRequest) -> PresalesDiagnosisOutcome:
        """E3 客户流失预警：查活跃度+流失评分。"""
        cid = request.customer_id or "C-001"
        activity = self.crm.query_customer_activity(customer_id=cid)
        churn = self.tools.score_customer_churn(cid)

        evidence: list[dict[str, object]] = []
        missing: list[str] = []

        if activity:
            a = activity[0]
            evidence.append(self._evidence("近30天跟进", f"{a.contact_count_30d}次"))
            evidence.append(self._evidence("近90天跟进", f"{a.contact_count_90d}次"))
            evidence.append(self._evidence("近90天拜访", f"{a.visit_count_90d}次"))
            evidence.append(self._evidence("近12月合同", f"{a.contract_count_12m}个"))
        else:
            missing.append("客户活跃度数据（MISSING）")

        evidence.append(self._evidence("流失风险评分", f"{churn.churn_score:.2f}（{churn.risk_level}）"))
        evidence.append(self._evidence("跟进递减趋势", "是" if churn.decline_trend else "否"))
        if churn.missing_field_visits > 0:
            evidence.append(self._evidence("缺失外勤次数", f"{churn.missing_field_visits}次"))

        conclusion = f"客户{cid}流失风险{churn.risk_level}（评分{churn.churn_score:.2f}），建议优先跟进。" if churn.churn_score >= 0.3 else "客户较为稳定。"
        return PresalesDiagnosisOutcome(
            scenario="E3", conclusion=conclusion,
            key_metrics=(("流失评分", f"{churn.churn_score:.2f}"), ("风险等级", churn.risk_level)),
            missing_items=tuple(missing), evidence=tuple(evidence),
            manual_review_required=churn.churn_score >= 0.3,
        )

    def _handle_e4(self, request: PresalesDiagnosisRequest) -> PresalesDiagnosisOutcome:
        """E4 报价竞争力：查最近标的偏离度。"""
        evidence: list[dict[str, object]] = []
        missing: list[str] = []
        lost_count = 0
        total_count = 0

        # 查询所有丢单商机做偏离分析
        opportunities = self.crm.query_opportunity_funnel(stage="丢单")
        for opp in opportunities:
            total_count += 1
            dev = self.tools.compute_quote_deviation(opp.opportunity_id)
            if dev.deviation_percent is not None:
                lost_count += 1
                evidence.append(self._evidence(
                    f"{opp.opportunity_id}偏离度",
                    f"我方{dev.our_quote:.0f}，竞品{dev.deviation_from_competitor:.0f}，偏差{dev.deviation_percent:.1%}"))
            else:
                missing.append(f"{opp.opportunity_id}竞品价（MISSING）")

        # 也查成交的做对比
        won = self.crm.query_opportunity_funnel(stage="成交")
        conclusion = f"最近{total_count}个丢单标的报价偏离度可分析，建议结合方案匹配度综合判断。" if lost_count > 0 else "竞品数据缺失，无法分析报价竞争力。"
        return PresalesDiagnosisOutcome(
            scenario="E4", conclusion=conclusion,
            key_metrics=(("丢单标数", f"{total_count}"), ("可分析偏离", f"{lost_count}")),
            missing_items=tuple(missing), evidence=tuple(evidence),
            manual_review_required=bool(missing),
        )

    def _handle_e5(self, request: PresalesDiagnosisRequest) -> PresalesDiagnosisOutcome:
        """E5 线索质量：分析各来源转化率。"""
        src = request.source
        evidence: list[dict[str, object]] = []

        if src:
            result = self.tools.analyze_lead_source(src)
            evidence.append(self._evidence(f"{src}来源", f"转化率{result.conversion_rate:.1%}，评级{result.quality_rating}"))
            conclusion = f"{src}来源转化率{result.conversion_rate:.1%}，评级{result.quality_rating}。{result.recommendation}"
        else:
            # 所有来源对比
            all_sources = self.crm.query_lead_quality()
            for s in all_sources:
                evidence.append(self._evidence(f"{s.lead_source}来源", f"转化率{s.conversion_rate:.1%}，线索{s.total_leads}"))
            conclusion = "各来源转化率对比完成，建议优化低转化率渠道。"

        return PresalesDiagnosisOutcome(
            scenario="E5", conclusion=conclusion,
            key_metrics=(("来源数", f"{len(all_sources) if not src else 1}"),),
            missing_items=(),
            evidence=tuple(evidence),
            manual_review_required=True,
        )
