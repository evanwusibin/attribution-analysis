"""索赔合规领域对象（S5 · 索赔工单合规性归因）。

对齐 specs Slice 5 与 `02_数据模型` 一.1：
- 质保资格判断与最终审批严格分离；
- 资格计算依赖规则版本（T5 质保手册、重新授权需求说明书）；
- 证据不足时只能输出建议与待补充清单，不得自动审批/拒赔/回写 DMS。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class WarrantyRule:
    """质保规则引用：手册版本、车型/总成/零件、时间/里程边界。"""

    rule_id: str
    vehicle_model: str
    assembly: str
    part_no: str | None
    warranty_months: int
    warranty_mileage: float
    rule_version: str
    source_class: Literal["FACT", "MOCK", "MISSING"]
    source_ref: str


@dataclass(frozen=True)
class MaintenanceRequirement:
    """保养要求：首保/定保节点、时间或里程先到原则。"""

    requirement_id: str
    maintenance_type: str
    interval_months: int | None
    interval_mileage: float | None
    rule_version: str
    source_class: Literal["FACT", "MOCK", "MISSING"]
    source_ref: str


@dataclass(frozen=True)
class ClaimEligibility:
    """索赔资格评估结果：是否符合、失败条件、证据链、待补充项。"""

    eligible: bool
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)
    supporting_evidence: tuple[str, ...] = field(default_factory=tuple)
    missing_items: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    manual_review_required: bool = True


@dataclass(frozen=True)
class ReauthorizationEligibility:
    """重新授权申请资格：可申请状态、类型、期限、前置条件。"""

    can_apply: bool
    failure_reasons: tuple[str, ...] = field(default_factory=tuple)
    requirements_met: tuple[str, ...] = field(default_factory=tuple)
    rule_version: str = ""
    source_class: Literal["FACT", "MOCK", "MISSING"] = "MISSING"
    source_ref: str = ""


@dataclass(frozen=True)
class ClaimSnapshot:
    """索赔单快照：业务外键、状态、金额、零件、工单关联。"""

    claim_id: str
    wo_id: str
    vin: str
    fault_desc: str
    parts_list: tuple[str, ...]
    claim_amount: float
    claim_status: str
    total_mileage: float
    created_at: str
    audit_date: str | None = None
    submit_count: int = 0
    authorization_status: str | None = None
    destruction_notice_generated: bool = False


@dataclass(frozen=True)
class VehicleSnapshot:
    """车辆快照：VIN、车型、交付日期、客户/合同。"""

    vin: str
    vehicle_model: str
    delivery_date: str
    customer_id: str
    contract_id: str
