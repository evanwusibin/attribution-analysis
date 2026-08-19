"""将已批准的业务场景映射为 Case 内的证据与候选结果。

该层只负责把场景服务的输出投影进公共归因生命周期；领域规则仍保留在各自的
售前和售后场景服务中。未声明的场景不会被推测或伪造。
"""
from __future__ import annotations

from dataclasses import dataclass

from attribution_analysis.application.scenarios.claim_compliance import ClaimComplianceRequest, ClaimComplianceService
from attribution_analysis.application.scenarios.after_sales import DiagnosisRequest, FaultDiagnosisService
from attribution_analysis.application.scenarios.presales import PresalesDiagnosisRequest, PresalesDiagnosisService


@dataclass(frozen=True)
class ScenarioEvidence:
    source_class: str
    source_ref: str
    rule_version: str
    content_summary: str


@dataclass(frozen=True)
class ScenarioProjection:
    conclusion: str
    key_metrics: tuple[dict[str, object], ...]
    missing_items: tuple[str, ...]
    evidence: tuple[ScenarioEvidence, ...]
    manual_review_required: bool


class BusinessScenarioRunner:
    """仅为 E1、E2、S1、S2 提供专项投影；其余目录场景保留通用双路归因。"""

    def __init__(
        self,
        presales: PresalesDiagnosisService,
        after_sales: FaultDiagnosisService,
        claim_compliance: ClaimComplianceService,
    ) -> None:
        """装配三个场景服务（售前/售后/索赔合规）。"""
        self.presales = presales
        self.after_sales = after_sales
        self.claim_compliance = claim_compliance

    def run(self, scenario_hint: str | None, question: str) -> ScenarioProjection | None:
        """按场景提示分发到专项投影；未声明场景返回 None。"""
        if scenario_hint in {"E1", "E2"}:
            return self._presales(question)
        if scenario_hint == "S1":
            return self._after_sales(question)
        if scenario_hint == "S2":
            return self._claim_compliance(question)
        return None

    def _presales(self, question: str) -> ScenarioProjection:
        """E1/E2 售前场景投影：运行诊断并把输出映射为 Case 证据。"""
        outcome = self.presales.run(PresalesDiagnosisRequest(question=question, region="华东"))
        return ScenarioProjection(
            conclusion=outcome.conclusion,
            key_metrics=tuple({"name": name, "value": value, "unit": "", "period": "本月"} for name, value in outcome.key_metrics),
            missing_items=outcome.missing_items,
            evidence=tuple(ScenarioEvidence(
                source_class=str(item["source_class"]),
                source_ref=str(item["source_ref"]),
                rule_version=str(item["rule_version"]),
                content_summary=str(item["content_summary"]),
            ) for item in outcome.evidence),
            manual_review_required=outcome.manual_review_required,
        )

    def _claim_compliance(self, question: str) -> ScenarioProjection:
        """S2 索赔合规投影：从问题提取索赔单号并投影资格结论。"""
        claim_id = next((token.strip("，。；,.?") for token in question.split() if token.startswith("CL-")), "CL-001")
        outcome = self.claim_compliance.run(ClaimComplianceRequest(question=question, claim_id=claim_id))
        missing_items = tuple(outcome.get("missing_items", ()))
        reasons = tuple(outcome.get("failure_reasons", ()))
        evidence = tuple(
            ScenarioEvidence("MOCK", f"claim.{claim_id}", "claim-compliance.demo.v1", item)
            for item in outcome.get("supporting_evidence", ())
        )
        evidence += tuple(
            ScenarioEvidence("MISSING", f"claim.{claim_id}", "claim-compliance.demo.v1", item)
            for item in missing_items
        )
        return ScenarioProjection(
            conclusion=str(outcome.get("recommendation", "索赔资格信息不足，需人工复核。")),
            key_metrics=(
                {"name": "索赔单", "value": claim_id, "unit": "", "period": "当前评估"},
                {"name": "置信度", "value": f"{float(outcome.get('confidence', 0)):.0%}", "unit": "", "period": "当前评估"},
            ),
            missing_items=missing_items + reasons,
            evidence=evidence,
            manual_review_required=True,
        )

    def _after_sales(self, question: str) -> ScenarioProjection:
        """S1 售后诊断投影：运行电池包故障诊断并映射证据。"""
        outcome = self.after_sales.run(DiagnosisRequest(question=question, vin="LSGAB52R7DF000005"))
        evidence = [
            ScenarioEvidence("MOCK", outcome.playbook_version, "battery.playbook.v1", hypothesis.cause_summary)
            for hypothesis in outcome.hypotheses
        ]
        evidence.extend(
            ScenarioEvidence("MISSING", "missing.items", "none", missing)
            for missing in outcome.missing_items
        )
        return ScenarioProjection(
            conclusion=outcome.conclusion,
            key_metrics=(
                {"name": "候选假设", "value": str(len(outcome.hypotheses)), "unit": "项", "period": "当前诊断"},
                {"name": "待补充", "value": str(len(outcome.missing_items)), "unit": "项", "period": "当前诊断"},
            ),
            missing_items=outcome.missing_items,
            evidence=tuple(evidence),
            manual_review_required=outcome.manual_review_required,
        )
