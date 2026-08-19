"""质保规则 Demo 适配器（S5 · 本地 MOCK 数据）。

对齐 specs Slice 5：
- 质保规则来源标记为 FACT（T5 手册）或 MOCK（演示阈值）；
- 保养节点、延保逻辑、零件来源均基于固定 seed 数据；
- 不连接真实 DMS/CRM，不执行自动审批/拒赔/回写操作。
"""
from __future__ import annotations

from attribution_analysis.domain.claim_compliance import (
    ClaimSnapshot,
    VehicleSnapshot,
    WarrantyRule,
    MaintenanceRequirement,
)
from attribution_analysis.ports.warranty import WarrantyPort


class DemoWarrantyAdapter(WarrantyPort):
    """质保规则 Demo 适配器：基于内存数据的 MOCK 实现。"""

    def __init__(self) -> None:
        """装载 MOCK 车辆/索赔/质保规则/保养要求/延保/领料等内存数据。"""
        # MOCK 车辆数据
        self.vehicles = {
            "LSGAB52R7DF000001": VehicleSnapshot(
                vin="LSGAB52R7DF000001",
                vehicle_model="T5",
                delivery_date="2024-01-15",
                customer_id="CUST-001",
                contract_id="CONTRACT-001",
            ),
            "LSGAB52R7DF000002": VehicleSnapshot(
                vin="LSGAB52R7DF000002",
                vehicle_model="T5",
                delivery_date="2021-06-10",
                customer_id="CUST-002",
                contract_id="CONTRACT-002",
            ),
            "LSGAB52R7DF000003": VehicleSnapshot(
                vin="LSGAB52R7DF000003",
                vehicle_model="T5",
                delivery_date="2021-06-10",
                customer_id="CUST-003",
                contract_id="CONTRACT-003",
            ),
        }

        # MOCK 索赔单数据
        self.claims = {
            "CL-001": ClaimSnapshot(
                claim_id="CL-001",
                wo_id="WO-001",
                vin="LSGAB52R7DF000001",
                fault_desc="电池包故障码 E104",
                parts_list=("P-201",),
                claim_amount=15000.0,
                claim_status="pending",
                total_mileage=35000.0,
                created_at="2024-08-10",
            ),
            "CL-002": ClaimSnapshot(
                claim_id="CL-002",
                wo_id="WO-002",
                vin="LSGAB52R7DF000002",
                fault_desc="电机故障",
                parts_list=("P-202",),
                claim_amount=22000.0,
                claim_status="pending",
                total_mileage=130000.0,  # 130000 在延保范围内（100000+50000=150000）
                created_at="2024-08-11",
            ),
            "CL-003": ClaimSnapshot(
                claim_id="CL-003",
                wo_id="WO-003",
                vin="LSGAB52R7DF000003",  # 不同车辆，无延保
                fault_desc="电机故障（无延保）",
                parts_list=("P-202",),
                claim_amount=22000.0,
                claim_status="pending",
                total_mileage=120000.0,
                created_at="2024-08-12",
            ),
            "CL-004": ClaimSnapshot(
                claim_id="CL-004",
                wo_id="WO-004",
                vin="LSGAB52R7DF000001",
                fault_desc="电池包故障，非原厂件",
                parts_list=("P-999",),
                claim_amount=12000.0,
                claim_status="pending",
                total_mileage=30000.0,
                created_at="2024-08-13",
            ),
            "CL-007": ClaimSnapshot(
                claim_id="CL-007",
                wo_id="WO-007",
                vin="LSGAB52R7DF000001",
                fault_desc="重新授权测试",
                parts_list=("P-201",),
                claim_amount=10000.0,
                claim_status="rejected",
                total_mileage=40000.0,
                created_at="2023-06-01",
                audit_date="2023-07-01",
                submit_count=1,
                authorization_status=None,
                destruction_notice_generated=False,
            ),
        }

        # MOCK 质保规则（基于 T5 手册）
        self.warranty_rules = {
            ("T5", "P-201"): WarrantyRule(
                rule_id="WR-T5-P201",
                vehicle_model="T5",
                assembly="电池包",
                part_no="P-201",
                warranty_months=36,
                warranty_mileage=100000.0,
                rule_version="T5_v1.0",
                source_class="FACT",
                source_ref="比亚迪混动轻卡T5保修保养手册_T45C10__docx.txt·质保政策",
            ),
            ("T5", "P-202"): WarrantyRule(
                rule_id="WR-T5-P202",
                vehicle_model="T5",
                assembly="电机",
                part_no="P-202",
                warranty_months=36,
                warranty_mileage=100000.0,
                rule_version="T5_v1.0",
                source_class="FACT",
                source_ref="比亚迪混动轻卡T5保修保养手册_T45C10__docx.txt·质保政策",
            ),
        }

        # MOCK 保养要求
        self.maintenance_requirements = {
            "first_service": MaintenanceRequirement(
                requirement_id="MR-FIRST",
                maintenance_type="首保",
                interval_months=3,
                interval_mileage=5000.0,
                rule_version="T5_v1.0",
                source_class="FACT",
                source_ref="比亚迪混动轻卡T5保修保养手册_T45C10__docx.txt·首次保养",
            ),
            "regular_service": MaintenanceRequirement(
                requirement_id="MR-REGULAR",
                maintenance_type="定保",
                interval_months=6,
                interval_mileage=30000.0,
                rule_version="T5_v1.0",
                source_class="FACT",
                source_ref="比亚迪混动轻卡T5保修保养手册_T45C10__docx.txt·定期保养",
            ),
        }

        # MOCK 延保记录
        self.extended_warranties = {
            ("LSGAB52R7DF000002", "P-202"): (True, 48, 50000.0),  # 延保48个月，150000km
        }

        # MOCK 领料记录（判断原厂件）
        self.parts_records = {
            ("CL-001", "P-201"): True,
            ("CL-002", "P-202"): True,
            ("CL-003", "P-202"): True,
            ("CL-004", "P-999"): False,
            ("CL-007", "P-201"): True,
        }

        # MOCK 保养记录
        self.maintenance_records = {
            "LSGAB52R7DF000001": {"complete": True, "missing": []},
            "LSGAB52R7DF000002": {"complete": True, "missing": []},
            "LSGAB52R7DF000003": {"complete": True, "missing": []},
        }

    def get_vehicle(self, vin: str) -> VehicleSnapshot | None:
        """按 VIN 查询车辆快照（MOCK）。"""
        return self.vehicles.get(vin)

    def get_claim(self, claim_id: str) -> ClaimSnapshot | None:
        """按索赔单号查询索赔快照（MOCK）。"""
        return self.claims.get(claim_id)

    def get_warranty_rule(self, vehicle_model: str, part_no: str) -> WarrantyRule | None:
        """按车型+零件号查询质保规则（T5 手册 FACT）。"""
        return self.warranty_rules.get((vehicle_model, part_no))

    def get_maintenance_requirement(self, maintenance_type: str) -> MaintenanceRequirement | None:
        """按保养类型查询保养要求（首保/定保）。"""
        return self.maintenance_requirements.get(maintenance_type)

    def check_maintenance_records(self, vin: str, delivery_date: str) -> tuple[bool, list[str]]:
        """检查保养记录完整性；返回 (是否完整, 缺失项)。"""
        record = self.maintenance_records.get(vin, {"complete": False, "missing": ["保养记录"]})
        return record["complete"], record["missing"]

    def check_part_origin(self, claim_id: str, part_no: str) -> tuple[bool, str]:
        """按领料记录判断是否原厂件；返回 (是否原厂, 证据说明)。"""
        is_original = self.parts_records.get((claim_id, part_no), False)
        evidence = "原厂件（领料记录）" if is_original else "非原厂件或无领料记录"
        return is_original, evidence

    def check_extended_warranty(self, vin: str, part_no: str) -> tuple[bool, int, float]:
        """查询延保记录；返回 (是否延保, 延保月数, 延保里程)。"""
        # 精确匹配 VIN 和零件号
        key = (vin, part_no)
        if key in self.extended_warranties:
            return self.extended_warranties[key]
        return False, 0, 0.0
