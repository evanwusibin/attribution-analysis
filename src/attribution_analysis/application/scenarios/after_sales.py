"""售后业务场景路由与故障诊断执行（S4）。

业务场景路由 → 故障域识别 → 诊断路径执行 → 候选根因。
首版实现 S1「故障报修与维修诊断」的电池包域；其他售后场景（S2~S5）与售前
场景（E1~E5）在各自切片获批后以同一模式扩展，不修改公共内核。
"""
from __future__ import annotations

from dataclasses import dataclass

from attribution_analysis.domain.fault_diagnosis import (
    FaultCase,
    FaultDiagnosisOutcome,
    RootCauseHypothesis,
)
from attribution_analysis.application.tools.fault_diagnosis import (
    INDUSTRY_MEAN_DEFECT_RATE,
    SOH_ANOMALY_THRESHOLD,
    BatteryPackDiagnosticTools,
    interpret_soh,
)


@dataclass(frozen=True)
class DiagnosisRequest:
    """售后故障诊断的输入：问题文本 + 可选显式定位。"""

    question: str
    vin: str | None = None
    claim_id: str | None = None
    wo_id: str | None = None
    batch_id: str | None = None


class AfterSalesScenarioRouter:
    """识别问题属于哪个售后场景；返回场景码或 None（不属于售后）。"""

    AFTER_SALES_KEYWORDS = ("索赔", "质保", "电池", "SOC", "SOH", "故障", "维修", "诊断", "延保", "保养", "批次", "不良率")

    def __init__(self) -> None:
        """绑定电池包诊断工具类（路由阶段不实例化）。"""
        self.diagnostic_tools = BatteryPackDiagnosticTools

    def route(self, question: str) -> str | None:
        """按关键词判断问题是否属于售后场景；不属于时返回 None。"""
        lowered = question.lower()
        for keyword in self.AFTER_SALES_KEYWORDS:
            if keyword in lowered:
                return "after_sales"
        return None


class FaultDiagnosisService:
    """S4 故障报修与维修诊断（电池包为首域）的执行服务。"""

    def __init__(self, after_sales) -> None:
        """装配售后只读适配器、诊断工具与场景路由。"""
        self.after_sales = after_sales
        self.tools = BatteryPackDiagnosticTools(after_sales)
        self.router = AfterSalesScenarioRouter()

    def is_after_sales(self, question: str) -> bool:
        """快捷判断：问题是否路由到售后场景。"""
        return self.router.route(question) == "after_sales"

    def run(self, request: DiagnosisRequest) -> FaultDiagnosisOutcome:
        """执行一次诊断：识别域 → 采集信号 → 生成候选假设与缺失清单。

        反例保证（specs Slice 4）：任何异常数值（SOH 低、不良率高、批次异常）
        只产生候选假设与人工复核，绝不自动拒赔/追偿/归责。
        """
        domain = self.tools.resolve_domain(request.question)
        if domain is None:
            return FaultDiagnosisOutcome(
                domain_code="unknown",
                playbook_version="none",
                missing_items=("未识别故障域：请补充症状描述或明确故障码",),
                manual_review_required=True,
                conclusion="无法路由到已实现的故障域，请人工判断。",
            )

        # 1) 采集原始信号（缺失即列入缺失清单）
        signals = self.tools.collect_signals(request.vin) if request.vin else ()
        missing: list[str] = []
        if request.vin and not signals:
            missing.append(f"缺少 {request.vin} 的电池健康快照")

        # 2) SOH 解释：阈值仅 MOCK，异常只能人工复核
        hypotheses: list[RootCauseHypothesis] = []
        soh_signal = next((s for s in signals if s.name == "SOH"), None)
        if soh_signal is not None:
            anomalous, verdict = interpret_soh(soh_signal, SOH_ANOMALY_THRESHOLD)
            supporting: list[str] = [verdict]
            counter: list[str] = []
            if anomalous:
                supporting.append(
                    f"SOH 阈值 {SOH_ANOMALY_THRESHOLD.threshold_value}% 为 MOCK 基准（{SOH_ANOMALY_THRESHOLD.rule_version}），"
                    "缺少检测方法与容量判定条款时不能认定自然衰减或质保免责。"
                )
                missing.append("检测方法与容量判定条款（FACT）")
                missing.append("诊断报告（FACT）")
            hypotheses.append(
                RootCauseHypothesis(
                    hypothesis_id="hyp_battery_degradation",
                    cause_summary="电池包健康度异常，疑似容量衰减",
                    supporting_evidence=tuple(supporting),
                    counter_evidence=tuple(counter),
                    confidence=0.5 if anomalous else 0.3,
                    review_required=anomalous,
                )
            )
        elif not signals and request.vin:
            missing.append("缺少 SOH 信号，无法给出健康度假设")

        # 3) 批次/供应商候选假设（G-C-1：异常聚集只能建议核验，不自动追偿）
        if request.batch_id:
            rate, rule = self.tools.check_batch(request.batch_id)
            if rule.source_class != "MISSING" and rate > INDUSTRY_MEAN_DEFECT_RATE.threshold_value:
                hypotheses.append(
                    RootCauseHypothesis(
                        hypothesis_id="hyp_batch_defect",
                        cause_summary=f"批次 {request.batch_id} 故障率 {rate:.0%} 高于行业均值 {INDUSTRY_MEAN_DEFECT_RATE.threshold_value:.0%}",
                        supporting_evidence=(
                            f"批次故障率 {rate:.0%}（{rule.source_class}）",
                            f"行业均值 {INDUSTRY_MEAN_DEFECT_RATE.threshold_value:.0%} 为 MOCK 基准",
                            "缺少采购质保合同与批次追溯时禁止自动发起反向索赔",
                        ),
                        counter_evidence=(),
                        confidence=0.6,
                        review_required=True,
                    )
                )
                missing.append("采购质保合同与批次追溯（MISSING）")

        # 4) 结论汇总
        review = any(h.review_required for h in hypotheses) or bool(missing)
        conclusion = "形成候选根因假设；证据等级为 MOCK，必须人工复核。" if review else "未发现异常信号，结论需人工确认。"

        return FaultDiagnosisOutcome(
            domain_code=domain.domain_code,
            playbook_version=domain.version,
            hypotheses=tuple(hypotheses),
            missing_items=tuple(missing),
            manual_review_required=review,
            conclusion=conclusion,
        )
