"""索赔合规场景服务（S5）。"""
from __future__ import annotations

from dataclasses import dataclass

from attribution_analysis.domain.claim_compliance import ClaimEligibility, ReauthorizationEligibility
from attribution_analysis.application.tools.warranty import WarrantyEligibilityTools
from attribution_analysis.ports.warranty import WarrantyPort


@dataclass(frozen=True)
class ClaimComplianceRequest:
    """索赔合规分析请求。"""

    question: str
    claim_id: str | None = None
    action: str = "evaluate"  # evaluate | reauthorize


class ClaimComplianceService:
    """S5 索赔合规场景服务：资格判断 + 重新授权资格。"""

    def __init__(self, warranty_port: WarrantyPort) -> None:
        """装配质保资格判断工具集。"""
        self.tools = WarrantyEligibilityTools(warranty_port)

    def is_claim_compliance(self, question: str) -> bool:
        """判断是否属于索赔合规场景。"""
        keywords = ("索赔", "质保", "保修", "赔付", "审批", "重新授权", "延保")
        lowered = question.lower()
        return any(kw in lowered for kw in keywords)

    def run(self, request: ClaimComplianceRequest) -> dict:
        """执行索赔合规分析。
        
        返回：
        - action=evaluate: ClaimEligibility
        - action=reauthorize: ReauthorizationEligibility
        """
        if not request.claim_id:
            return {
                "error": "缺少 claim_id",
                "suggestion": "请提供索赔单号",
            }

        if request.action == "reauthorize":
            result = self.tools.evaluate_reauthorization_eligibility(request.claim_id)
            return {
                "action": "reauthorize",
                "claim_id": request.claim_id,
                "can_apply": result.can_apply,
                "failure_reasons": result.failure_reasons,
                "requirements_met": result.requirements_met,
                "rule_version": result.rule_version,
                "source_class": result.source_class,
                "source_ref": result.source_ref,
            }
        else:
            result = self.tools.evaluate_claim_eligibility(request.claim_id)
            return {
                "action": "evaluate",
                "claim_id": request.claim_id,
                "eligible": result.eligible,
                "failure_reasons": result.failure_reasons,
                "supporting_evidence": result.supporting_evidence,
                "missing_items": result.missing_items,
                "confidence": result.confidence,
                "manual_review_required": result.manual_review_required,
                "recommendation": self._generate_recommendation(result),
            }

    def _generate_recommendation(self, eligibility: ClaimEligibility) -> str:
        """生成建议（不是审批结论）。"""
        if eligibility.eligible and eligibility.confidence >= 0.9:
            return "建议赔付（所有条件符合）"
        elif eligibility.eligible and eligibility.confidence < 0.9:
            return f"建议赔付，但置信度 {eligibility.confidence:.1%}，需人工复核"
        elif eligibility.missing_items:
            return f"证据不足，需补充：{', '.join(eligibility.missing_items)}"
        else:
            return f"建议拒赔（{', '.join(eligibility.failure_reasons)}）"
