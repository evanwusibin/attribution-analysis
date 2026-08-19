"""售后共享证据底座的能力端口。

契约要点（对齐 specs S3）：
- 只读语义视图：调用方只描述查询意图，不传任意 SQL；
- 来源版本化：每条载荷携带 `source_class`/`source_ref`/`rule_version`，供 Evidence 回溯源；
- 模拟隔离：演示库数据一律 `MOCK`，FACT 规则（如 T5 质保手册）单独标注。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VehicleSnapshot:
    vin: str
    vehicle_model: str
    delivery_date: str
    battery_software_version: str
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class WorkOrderSnapshot:
    wo_id: str
    vin: str
    fault_code: str | None
    fault_desc: str | None
    fault_date: str | None
    mileage: float
    meter_replaced: bool
    prev_wo_id: str | None
    ticket_type: str
    status: str
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class ClaimSnapshot:
    claim_id: str
    wo_id: str
    vin: str
    fault_desc: str | None
    parts_list_json: str | None
    claim_amount: float
    claim_reason: str | None
    claim_status: str
    total_mileage: float
    authorization_status: str
    audit_date: str | None
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class PartSnapshot:
    part_no: str
    part_name: str
    assembly: str
    warranty_type: str
    warranty_months: int | None
    warranty_mileage: float | None
    is_original: bool
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class BatteryHealthSnapshot:
    vin: str
    soh: float
    cycle_count: int
    capacity: float
    degradation_rate: float
    soc: float
    test_date: str
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class WarrantyManualSnapshot:
    vehicle_model: str
    assembly: str
    part_no: str
    warranty_months: int
    warranty_mileage: float
    exclusion_clause: str | None
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class MaintenanceSnapshot:
    vin: str
    maintenance_type: str
    mileage_at_service: float
    service_date: str
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class SupplierSnapshot:
    supplier_id: str
    supplier_name: str
    defect_rate: float
    warranty_months: int
    source_class: str
    source_ref: str
    rule_version: str


@dataclass(frozen=True)
class BatchSnapshot:
    batch_id: str
    part_no: str
    supplier_id: str
    total_units: int
    failed_units: int
    defect_rate: float
    source_class: str
    source_ref: str
    rule_version: str


class AfterSalesPort(Protocol):
    """售后业务数据的只读语义视图。实现不得执行任意 SQL。"""

    def get_vehicle(self, vin: str) -> VehicleSnapshot | None:
        """按 VIN 查询车辆信息（只读语义视图）。"""
        ...

    def list_work_orders(self, vin: str) -> tuple[WorkOrderSnapshot, ...]:
        """按 VIN 列出全部工单。"""
        ...

    def get_claim(self, claim_id: str) -> ClaimSnapshot | None:
        """按索赔单号查询索赔信息。"""
        ...

    def get_part(self, part_no: str) -> PartSnapshot | None:
        """按零件号查询零件主数据。"""
        ...

    def get_battery_health(self, vin: str) -> BatteryHealthSnapshot | None:
        """按 VIN 查询电池健康快照。"""
        ...

    def get_warranty_manual(self, part_no: str, vehicle_model: str | None = None) -> WarrantyManualSnapshot | None:
        """按零件（可选车型）查询质保手册条款。"""
        ...

    def list_maintenance(self, vin: str) -> tuple[MaintenanceSnapshot, ...]:
        """按 VIN 列出保养记录。"""
        ...

    def get_supplier(self, supplier_id: str) -> SupplierSnapshot | None:
        """按供应商 ID 查询不良率与质保期。"""
        ...

    def get_batch(self, batch_id: str) -> BatchSnapshot | None:
        """按批次号查询批次故障率。"""
        ...