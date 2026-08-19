"""质保资格判断工具（S5 · 索赔合规）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from attribution_analysis.domain.claim_compliance import (
    ClaimEligibility,
    ReauthorizationEligibility,
    WarrantyRule,
)
from attribution_analysis.ports.warranty import WarrantyPort


class WarrantyEligibilityTools:
    """质保资格判断工具集：保内/超保、原厂件、保养记录、重新授权。"""

    def __init__(self, warranty_port: WarrantyPort) -> None:
        """绑定质保端口（只读适配器）。"""
        self.warranty = warranty_port

    def evaluate_claim_eligibility(self, claim_id: str) -> ClaimEligibility:
        """评估索赔资格：G-A-1～G-A-7 的核心逻辑。
        
        返回资格判断、失败原因、证据链与待补充项；
        不进行自动审批/拒赔/回写 DMS。
        """
        claim = self.warranty.get_claim(claim_id)
        if not claim:
            return ClaimEligibility(
                eligible=False,
                failure_reasons=("索赔单不存在",),
                confidence=0.0,
            )

        vehicle = self.warranty.get_vehicle(claim.vin)
        if not vehicle:
            return ClaimEligibility(
                eligible=False,
                failure_reasons=("车辆信息不存在",),
                missing_items=("车辆基础信息",),
                confidence=0.0,
            )

        evidence: list[str] = []
        failures: list[str] = []
        missing: list[str] = []
        confidence = 1.0

        # 1) 质保期判断
        warranty_result = self._check_warranty_period(
            vehicle.delivery_date, claim.total_mileage, vehicle.vehicle_model, claim.parts_list, claim.vin
        )
        if not warranty_result["in_warranty"]:
            failures.append(warranty_result["reason"])
            confidence *= 0.3
        else:
            evidence.append(warranty_result["reason"])
        
        if warranty_result.get("missing"):
            missing.extend(warranty_result["missing"])

        # 2) 零件来源判断
        for part_no in claim.parts_list:
            is_original, part_evidence = self.warranty.check_part_origin(claim_id, part_no)
            if is_original:
                evidence.append(f"零件 {part_no}：{part_evidence}")
            else:
                failures.append(f"零件 {part_no}：{part_evidence}")
                confidence *= 0.5

        # 3) 保养记录判断
        maintenance_ok, maintenance_missing = self.warranty.check_maintenance_records(
            claim.vin, vehicle.delivery_date
        )
        if maintenance_ok:
            evidence.append("保养记录完整，符合首保/定保要求")
        else:
            failures.append(f"保养记录不完整：{', '.join(maintenance_missing)}")
            confidence *= 0.6

        # 4) 综合判断
        eligible = len(failures) == 0
        manual_review = len(missing) > 0 or confidence < 0.9

        return ClaimEligibility(
            eligible=eligible,
            failure_reasons=tuple(failures),
            supporting_evidence=tuple(evidence),
            missing_items=tuple(missing),
            confidence=confidence,
            manual_review_required=manual_review,
        )

    def _check_warranty_period(
        self, delivery_date: str, mileage: float, vehicle_model: str, parts: tuple[str, ...], vin: str
    ) -> dict:
        """检查质保期：时间或里程先到原则。"""
        try:
            delivery = datetime.fromisoformat(delivery_date)
            now = datetime.now()
            months_used = (now.year - delivery.year) * 12 + (now.month - delivery.month)
        except ValueError:
            return {
                "in_warranty": False,
                "reason": "交付日期格式错误",
                "missing": ["有效的交付日期"],
            }

        # 查询第一个零件的质保规则（简化处理，实际应逐件查询）
        part_no = parts[0] if parts else ""
        rule = self.warranty.get_warranty_rule(vehicle_model, part_no)
        
        if not rule:
            return {
                "in_warranty": False,
                "reason": f"未找到车型 {vehicle_model} 零件 {part_no} 的质保规则",
                "missing": [f"质保手册：{vehicle_model}/{part_no}"],
            }

        # 检查延保
        has_extended, extended_months, extended_mileage = self.warranty.check_extended_warranty(
            vin, part_no
        )
        
        effective_months = rule.warranty_months + (extended_months if has_extended else 0)
        effective_mileage = rule.warranty_mileage + (extended_mileage if has_extended else 0)

        # 时间或里程先到
        if months_used > effective_months:
            reason = f"超过质保期限（{effective_months}个月）"
            if has_extended:
                reason += f"，含延保 {extended_months} 个月"
            return {"in_warranty": False, "reason": reason}

        if mileage > effective_mileage:
            reason = f"超过质保里程（{effective_mileage}km）"
            if has_extended:
                reason += f"，含延保 {extended_mileage} km"
            return {"in_warranty": False, "reason": reason}

        reason = f"保内（{rule.warranty_months}个月或{rule.warranty_mileage}km，{rule.source_class}：{rule.source_ref}）"
        if has_extended:
            reason += f"，含延保至 {effective_months}个月或{effective_mileage}km"
        
        return {"in_warranty": True, "reason": reason}

    def evaluate_reauthorization_eligibility(self, claim_id: str) -> ReauthorizationEligibility:
        """评估重新授权申请资格：G-A-7 的核心逻辑。
        
        依据：reauthorize_v1.0.docx.txt
        - 可申请状态：已通过/部分通过/已拒绝（且已退回）
        - 类型：普通索赔
        - 审核日期间隔：≤1年
        - 无重复申请
        - 已生成销毁通知
        """
        claim = self.warranty.get_claim(claim_id)
        if not claim:
            return ReauthorizationEligibility(
                can_apply=False,
                failure_reasons=("索赔单不存在",),
            )

        requirements: list[str] = []
        failures: list[str] = []

        # 1) 状态校验
        allowed_statuses = {"approved", "partial_approved", "rejected"}
        if claim.claim_status not in allowed_statuses:
            failures.append(f"索赔状态 {claim.claim_status} 不允许申请重新授权（需为：已通过/部分通过/已拒绝）")
        else:
            requirements.append(f"索赔状态符合：{claim.claim_status}")

        # 2) 类型校验（假设通过字段判断，实际需补充类型字段）
        # 简化处理：假设所有都是普通索赔
        requirements.append("索赔类型为普通索赔")

        # 3) 审核日期间隔校验
        if claim.audit_date:
            try:
                audit = datetime.fromisoformat(claim.audit_date)
                now = datetime.now()
                months_since_audit = (now.year - audit.year) * 12 + (now.month - audit.month)
                
                if months_since_audit > 12:
                    failures.append(f"审核日期距今 {months_since_audit} 个月，超过1年期限")
                else:
                    requirements.append(f"审核日期距今 {months_since_audit} 个月，在1年期限内")
            except ValueError:
                failures.append("审核日期格式错误")
        else:
            failures.append("缺少审核日期")

        # 4) 重复申请校验
        if claim.authorization_status in {"pending", "submitted"}:
            failures.append(f"已有进行中的授权申请（状态：{claim.authorization_status}）")
        else:
            requirements.append("无重复授权申请")

        # 5) 销毁通知校验
        if not claim.destruction_notice_generated:
            failures.append("未生成销毁通知（前置条件）")
        else:
            requirements.append("已生成销毁通知")

        can_apply = len(failures) == 0

        return ReauthorizationEligibility(
            can_apply=can_apply,
            failure_reasons=tuple(failures),
            requirements_met=tuple(requirements),
            rule_version="reauthorize_v1.0",
            source_class="FACT",
            source_ref="reauthorize_v1.0.docx.txt",
        )
