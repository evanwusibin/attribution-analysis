"""质保规则与索赔资格查询端口（S5）。"""
from __future__ import annotations

from abc import ABC, abstractmethod

from attribution_analysis.domain.claim_compliance import (
    ClaimSnapshot,
    VehicleSnapshot,
    WarrantyRule,
    MaintenanceRequirement,
    ClaimEligibility,
    ReauthorizationEligibility,
)


class WarrantyPort(ABC):
    """质保规则与索赔资格查询能力契约。"""

    @abstractmethod
    def get_vehicle(self, vin: str) -> VehicleSnapshot | None:
        """查询车辆快照。"""

    @abstractmethod
    def get_claim(self, claim_id: str) -> ClaimSnapshot | None:
        """查询索赔单快照。"""

    @abstractmethod
    def get_warranty_rule(self, vehicle_model: str, part_no: str) -> WarrantyRule | None:
        """查询质保规则：根据车型和零件号。"""

    @abstractmethod
    def get_maintenance_requirement(self, maintenance_type: str) -> MaintenanceRequirement | None:
        """查询保养要求：首保/定保节点。"""

    @abstractmethod
    def check_maintenance_records(self, vin: str, delivery_date: str) -> tuple[bool, list[str]]:
        """校验保养记录完整性：返回（是否合规，缺失项列表）。"""

    @abstractmethod
    def check_part_origin(self, claim_id: str, part_no: str) -> tuple[bool, str]:
        """校验零件来源：返回（是否原厂件，证据说明）。"""

    @abstractmethod
    def check_extended_warranty(self, vin: str, part_no: str) -> tuple[bool, int, float]:
        """查询延保：返回（是否有延保，延长月数，延长里程）。"""
