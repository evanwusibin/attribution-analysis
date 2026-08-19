"""售后共享证据底座的 DuckDB 只读适配器。

只暴露端口定义的语义视图；查询 SQL 全部为白名单固定语句，不接受任意输入拼接。
演示库数据一律标记 `MOCK`（seed=42 模拟样例）；FACT 规则来源（如 T5 质保手册）
通过 `rule_version` 与 `source_ref` 显式标识。
"""
from __future__ import annotations

from duckdb import DuckDBPyConnection

from attribution_analysis.ports.after_sales import (
    AfterSalesPort,
    BatchSnapshot,
    BatteryHealthSnapshot,
    ClaimSnapshot,
    MaintenanceSnapshot,
    PartSnapshot,
    SupplierSnapshot,
    VehicleSnapshot,
    WarrantyManualSnapshot,
    WorkOrderSnapshot,
)

MOCK_REF = "demo.duckdb.after_sales.v1"
MOCK_RULE = "warranty.t5.v1"
MANUAL_RULE = "manual.t5.v1"


def _row_to_snapshot(row: tuple | None, factory: callable) -> object | None:
    """把查询行转换为端口快照；None 时返回 None。"""
    if row is None:
        return None
    return factory(*row)


class DemoAfterSalesAdapter(AfterSalesPort):
    def __init__(self, connection: DuckDBPyConnection) -> None:
        """绑定演示数据库只读连接。"""
        self.connection = connection

    def get_vehicle(self, vin: str) -> VehicleSnapshot | None:
        """按 VIN 查询车辆信息（只读白名单）。"""
        row = self.connection.execute(
            "SELECT vin, vehicle_model, delivery_date, battery_software_version FROM vehicles WHERE vin = ?",
            [vin],
        ).fetchone()
        return _row_to_snapshot(row, lambda *v: VehicleSnapshot(*v, "MOCK", MOCK_REF, MOCK_RULE))

    def list_work_orders(self, vin: str) -> tuple[WorkOrderSnapshot, ...]:
        """按 VIN 列出全部工单。"""
        rows = self.connection.execute(
            "SELECT wo_id, vin, fault_code, fault_desc, fault_date, mileage, meter_replaced, "
            "prev_wo_id, ticket_type, status FROM work_orders WHERE vin = ? ORDER BY created_at",
            [vin],
        ).fetchall()
        return tuple(
            WorkOrderSnapshot(
                *row,
                source_class="MOCK",
                source_ref=MOCK_REF,
                rule_version=MOCK_RULE,
            )
            for row in rows
        )

    def get_claim(self, claim_id: str) -> ClaimSnapshot | None:
        """按索赔单号查询索赔信息。"""
        row = self.connection.execute(
            "SELECT claim_id, wo_id, vin, fault_desc, parts_list_json, claim_amount, claim_reason, "
            "claim_status, total_mileage, authorization_status, audit_date FROM claims WHERE claim_id = ?",
            [claim_id],
        ).fetchone()
        return _row_to_snapshot(row, lambda *v: ClaimSnapshot(*v, "MOCK", MOCK_REF, MOCK_RULE))

    def get_part(self, part_no: str) -> PartSnapshot | None:
        """按零件号查询零件主数据与质保类型。"""
        row = self.connection.execute(
            "SELECT part_no, part_name, assembly, warranty_type, warranty_months, warranty_mileage, "
            "is_original FROM parts_master WHERE part_no = ?",
            [part_no],
        ).fetchone()
        return _row_to_snapshot(row, lambda *v: PartSnapshot(*v, "MOCK", MOCK_REF, MOCK_RULE))

    def get_battery_health(self, vin: str) -> BatteryHealthSnapshot | None:
        """按 VIN 查询电池健康快照（SOH/循环/容量）。"""
        row = self.connection.execute(
            "SELECT vin, soh, cycle_count, capacity, degradation_rate, soc, test_date "
            "FROM battery_health WHERE vin = ?",
            [vin],
        ).fetchone()
        return _row_to_snapshot(row, lambda *v: BatteryHealthSnapshot(*v, "MOCK", MOCK_REF, MOCK_RULE))

    def get_warranty_manual(self, part_no: str, vehicle_model: str | None = None) -> WarrantyManualSnapshot | None:
        """按零件（可选车型）查询质保手册条款（T5 手册规则）。"""
        if vehicle_model:
            row = self.connection.execute(
                "SELECT vehicle_model, assembly, part_no, warranty_months, warranty_mileage, exclusion_clause "
                "FROM warranty_manuals WHERE part_no = ? AND vehicle_model = ?",
                [part_no, vehicle_model],
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT vehicle_model, assembly, part_no, warranty_months, warranty_mileage, exclusion_clause "
                "FROM warranty_manuals WHERE part_no = ?",
                [part_no],
            ).fetchone()
        return _row_to_snapshot(row, lambda *v: WarrantyManualSnapshot(*v, "MOCK", MOCK_REF, MANUAL_RULE))

    def list_maintenance(self, vin: str) -> tuple[MaintenanceSnapshot, ...]:
        """按 VIN 列出全部保养记录（含里程与服务日期）。"""
        rows = self.connection.execute(
            "SELECT vin, maintenance_type, mileage_at_service, service_date "
            "FROM maintenance_records WHERE vin = ? ORDER BY service_date",
            [vin],
        ).fetchall()
        return tuple(
            MaintenanceSnapshot(
                *row,
                source_class="MOCK",
                source_ref=MOCK_REF,
                rule_version=MOCK_RULE,
            )
            for row in rows
        )

    def get_supplier(self, supplier_id: str) -> SupplierSnapshot | None:
        """按供应商 ID 查询不良率与质保期。"""
        row = self.connection.execute(
            "SELECT supplier_id, supplier_name, defect_rate, warranty_months FROM suppliers WHERE supplier_id = ?",
            [supplier_id],
        ).fetchone()
        return _row_to_snapshot(row, lambda *v: SupplierSnapshot(*v, "MOCK", MOCK_REF, MOCK_RULE))

    def get_batch(self, batch_id: str) -> BatchSnapshot | None:
        """按批次号查询批次故障率。"""
        row = self.connection.execute(
            "SELECT batch_id, part_no, supplier_id, total_units, failed_units, defect_rate "
            "FROM part_batches WHERE batch_id = ?",
            [batch_id],
        ).fetchone()
        return _row_to_snapshot(row, lambda *v: BatchSnapshot(*v, "MOCK", MOCK_REF, MOCK_RULE))

