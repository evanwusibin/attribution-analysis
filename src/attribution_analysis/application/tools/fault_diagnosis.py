"""电池包诊断域的业务工具（S4 首个完整诊断域）。

规则边界（对齐 `02_数据模型` 三、业务资产映射）：
- 信号字段（SOH/SOC/循环次数/衰减率/容量）本身为 `FACT`（BMS/诊断仪上报）；
- 故障率、行业均值、SOH 阈值均为 `MOCK`——阈值解释必须带版本，只能产生候选根因与人工复核；
- 缺少检测方法、容量判定条款或诊断报告时，进入 `needs_input`，不得输出自然衰减、拒赔或追偿裁决。
"""
from __future__ import annotations

from attribution_analysis.domain.fault_diagnosis import (
    DiagnosticSignal,
    FaultCase,
    FaultDomain,
    RuleReference,
)

# 电池包域声明：症状关键词与适用车型
BATTERY_DOMAIN = FaultDomain(
    domain_code="battery_pack",
    name="电池包",
    applicable_models=("T5轻卡",),
    symptom_keywords=("电池", "SOC", "SOH", "续航", "掉电", "容量", "衰减", "充电"),
    version="battery.playbook.v1",
)

# 行业均值与异常阈值：MOCK（无原始制度依据，禁止作为 FACT 结论依据）
INDUSTRY_MEAN_DEFECT_RATE = RuleReference(
    rule_name="行业均值故障率",
    rule_version="industry.benchmark.v1",
    source_class="MOCK",
    source_ref="demo.mock.threshold.v1",
    threshold_value=0.02,
)

SOH_ANOMALY_THRESHOLD = RuleReference(
    rule_name="SOH 异常判定阈值",
    rule_version="battery.threshold.v1",
    source_class="MOCK",
    source_ref="demo.mock.threshold.v1",
    threshold_value=75.0,
)


class BatteryPackDiagnosticTools:
    """电池包诊断工具：全部只读，输出带来源等级的信号与规则引用。"""

    def __init__(self, after_sales) -> None:
        """绑定售后只读适配器。"""
        self.after_sales = after_sales

    def resolve_domain(self, symptom: str) -> FaultDomain | None:
        """故障域识别：症状命中关键词即映射到电池包域（首版单域）。"""
        lowered = symptom.lower()
        if any(keyword in lowered for keyword in BATTERY_DOMAIN.symptom_keywords):
            return BATTERY_DOMAIN
        return None

    def collect_signals(self, vin: str) -> tuple[DiagnosticSignal, ...]:
        """采集原始诊断信号（来源为模拟库，一律 MOCK 但字段本身有出处）。"""
        health = self.after_sales.get_battery_health(vin)
        if health is None:
            return ()
        return (
            DiagnosticSignal("SOH", health.soh, "%", health.test_date, health.source_class, health.source_ref),
            DiagnosticSignal("cycle_count", health.cycle_count, "次", health.test_date, health.source_class, health.source_ref),
            DiagnosticSignal("capacity", health.capacity, "Ah", health.test_date, health.source_class, health.source_ref),
            DiagnosticSignal("degradation_rate", health.degradation_rate, "", health.test_date, health.source_class, health.source_ref),
            DiagnosticSignal("SOC", health.soc, "%", health.test_date, health.source_class, health.source_ref),
        )

    def check_defect_rate(self, supplier_id: str) -> tuple[float, RuleReference]:
        """供应商不良率（首版统计值为 MOCK，仅作候选假设依据）。"""
        supplier = self.after_sales.get_supplier(supplier_id)
        if supplier is None:
            return 0.0, RuleReference(
                rule_name="供应商不良率",
                rule_version="supplier.defect.v1",
                source_class="MISSING",
                source_ref="missing.supplier",
            )
        return supplier.defect_rate, RuleReference(
            rule_name="供应商不良率",
            rule_version="supplier.defect.v1",
            source_class=supplier.source_class,
            source_ref=supplier.source_ref,
            threshold_value=supplier.defect_rate,
        )

    def check_batch(self, batch_id: str) -> tuple[float, RuleReference]:
        """批次故障率（G-C-1：与行业均值对比，仅形成候选假设）。"""
        batch = self.after_sales.get_batch(batch_id)
        if batch is None:
            return 0.0, RuleReference(
                rule_name="批次故障率",
                rule_version="batch.defect.v1",
                source_class="MISSING",
                source_ref="missing.batch",
            )
        return batch.defect_rate, RuleReference(
            rule_name="批次故障率",
            rule_version="batch.defect.v1",
            source_class=batch.source_class,
            source_ref=batch.source_ref,
            threshold_value=batch.defect_rate,
        )


def interpret_soh(signal: DiagnosticSignal, rule: RuleReference) -> tuple[bool, str]:
    """SOH 解释：阈值仅 MOCK 时，任何异常判定都必须人工复核。"""
    if rule.source_class == "MISSING":
        return False, "缺少 SOH 判定规则，只能人工复核。"
    anomalous = signal.value < rule.threshold_value
    verdict = "低于 MOCK 阈值，疑似异常" if anomalous else "处于正常范围（按 MOCK 阈值）"
    return anomalous, verdict