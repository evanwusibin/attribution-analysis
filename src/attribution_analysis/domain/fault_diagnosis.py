"""故障诊断域的领域对象（S4 · 电池包为首个完整实现域）。

对齐 specs Slice 4 与 `02_数据模型` 一.4：
- 故障域不是新的 Agent 流程，而是同一归因内核可加载的业务配置；
- 原始信号与解释结果分离：`DiagnosticSignal` 只携带采集值，阈值解释独立引用规则版本；
- 证据不足时只能输出候选假设并标记人工复核，绝不自动归责/拒赔/追偿。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FaultDomain:
    """声明一个故障域：适用车型、症状/DTC、版本与升级条件。"""

    domain_code: str
    name: str
    applicable_models: tuple[str, ...]
    symptom_keywords: tuple[str, ...]
    version: str


@dataclass(frozen=True)
class DiagnosticSignal:
    """原始检测信号：值与来源分离，解释必须引用规则版本。"""

    name: str
    value: float
    unit: str
    collected_at: str
    source_class: str
    source_ref: str


@dataclass(frozen=True)
class RuleReference:
    """阈值/规则解释的引用：保证任何数值判断可回溯。"""

    rule_name: str
    rule_version: str
    source_class: str
    source_ref: str
    threshold_value: float | None = None


@dataclass(frozen=True)
class DiagnosticPlaybook:
    """版本化诊断路径：检查顺序、所需证据、排除条件与人工升级条件。"""

    playbook_id: str
    domain_code: str
    version: str
    check_order: tuple[str, ...]
    required_signals: tuple[str, ...]
    manual_upgrade_conditions: tuple[str, ...]


@dataclass(frozen=True)
class RootCauseHypothesis:
    """候选根因：支持/反证证据、置信度与人工复核状态。"""

    hypothesis_id: str
    cause_summary: str
    supporting_evidence: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    confidence: float
    review_required: bool = True


@dataclass(frozen=True)
class FaultDiagnosisOutcome:
    """一次诊断的执行结果：候选假设 + 缺失清单 + 是否需人工复核。"""

    domain_code: str
    playbook_version: str
    hypotheses: tuple[RootCauseHypothesis, ...] = field(default_factory=tuple)
    missing_items: tuple[str, ...] = field(default_factory=tuple)
    manual_review_required: bool = False
    conclusion: str = ""


@dataclass(frozen=True)
class FaultCase:
    """一次待分析的故障：VIN、工单、症状、故障码、当前里程与故障域。"""

    vin: str
    wo_id: str
    symptom: str
    fault_code: str | None
    current_mileage: float
    domain_code: str