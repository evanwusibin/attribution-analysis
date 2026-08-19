"""S6 重复维修与客户投诉归因领域对象。"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComplaintSnapshot:
    complaint_id: str
    vin: str
    complaint_type: str
    complaint_content: str
    severity: str
    status: str
    source_class: str = "MOCK"
    source_ref: str = "demo.duckdb.after_sales.v1"
    rule_version: str = "complaint.v1"


@dataclass(frozen=True)
class RepairAttemptSnapshot:
    attempt_id: str
    wo_id: str
    vin: str
    fault_code: str
    repair_action: str
    parts_replaced: str
    tech_id: str
    result: str
    is_recurring: bool
    repair_date: str
    source_class: str = "MOCK"
    source_ref: str = "demo.duckdb.after_sales.v1"
    rule_version: str = "repair.v1"


@dataclass(frozen=True)
class TechnicianSnapshot:
    tech_id: str
    name: str
    station_code: str
    specialty: str
    total_repairs: int
    successful_repairs: int
    avg_repair_time_hours: float
    certification_level: str
    source_class: str = "MOCK"
    source_ref: str = "demo.duckdb.after_sales.v1"
    rule_version: str = "tech.v1"


@dataclass(frozen=True)
class SLAEventSnapshot:
    event_id: str
    wo_id: str
    station_code: str
    event_type: str
    scheduled_time: str
    actual_time: str
    delay_hours: float
    is_overdue: bool
    source_class: str = "MOCK"
    source_ref: str = "demo.duckdb.after_sales.v1"
    rule_version: str = "sla.v1"


@dataclass(frozen=True)
class ComplaintAnalysisOutcome:
    """S6 诊断输出（六段结构同构）。"""
    scenario: str
    conclusion: str
    key_metrics: tuple[tuple[str, str], ...]
    missing_items: tuple[str, ...]
    evidence: tuple[dict[str, object], ...]
    manual_review_required: bool