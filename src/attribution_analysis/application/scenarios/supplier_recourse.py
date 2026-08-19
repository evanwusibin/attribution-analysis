"""S8 供应商反向索赔归因服务。"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SupplierRecourseRequest:
    question: str
    supplier_id: str | None = None
    claim_id: str | None = None
    batch_id: str | None = None


SUPPLIER_KEYWORDS = ("供应商", "追偿", "反向索赔", "批次", "不良率", "质量索赔")


class SupplierRecourseService:
    """S8 供应商质量与反向索赔归因执行服务。"""

    def __init__(self, connection) -> None:
        """绑定演示数据库连接。"""
        self.conn = connection

    def is_supplier_scenario(self, question: str) -> bool:
        """判断问题是否属于供应商追偿场景。"""
        return any(kw in question for kw in SUPPLIER_KEYWORDS)

    def run(self, request: SupplierRecourseRequest) -> dict:
        """执行追偿候选评估：合同在期 + 不良率超均值 + 批次异常。"""
        supplier_id = request.supplier_id or ""
        claim_id = request.claim_id or ""
        evidence: list[dict[str, object]] = []
        missing: list[str] = []
        metrics: list[tuple[str, str]] = []

        # 1. 查供应商基本信息
        if supplier_id:
            supplier = self.conn.execute(
                "SELECT supplier_id, supplier_name, defect_rate, warranty_months FROM suppliers WHERE supplier_id = ?",
                [supplier_id],
            ).fetchone()
        else:
            supplier = self.conn.execute(
                "SELECT supplier_id, supplier_name, defect_rate, warranty_months FROM suppliers ORDER BY defect_rate DESC LIMIT 1",
                [],
            ).fetchone()

        if not supplier:
            missing.append("供应商信息（MISSING）")
            return self._build_outcome("未找到供应商数据", [], missing, metrics, True)

        sid, sname, defect_rate, war_months = supplier
        evidence.append({
            "source_class": "MOCK",
            "source_ref": "demo.duckdb.after_sales.v1",
            "rule_version": "supplier.v1",
            "content_summary": f"供应商 {sname}（{sid}）：不良率 {defect_rate}，质保期 {war_months} 个月",
        })
        metrics.append(("不良率", f"{defect_rate}"))
        industry_avg = 0.02  # MOCK 阈值
        if defect_rate > industry_avg:
            evidence.append({
                "source_class": "MOCK",
                "source_ref": "demo.duckdb.after_sales.v1",
                "rule_version": "supplier.v1",
                "content_summary": f"不良率 {defect_rate} 高于行业均值 {industry_avg}（MOCK）",
            })

        # 2. 查采购质保合同
        contracts = self.conn.execute(
            "SELECT id, contract_no, warranty_months, warranty_mileage, start_date, end_date, status FROM supplier_warranty_contracts WHERE supplier_id = ?",
            [sid],
        ).fetchall()

        if contracts:
            for c in contracts:
                evidence.append({
                    "source_class": "MOCK",
                    "source_ref": "demo.duckdb.after_sales.v1",
                    "rule_version": "contract.v1",
                    "content_summary": f"采购合同 {c[1]}：质保 {c[2]} 个月/{c[3]} km，{c[4]}~{c[5]}，状态 {c[6]}",
                })
        else:
            missing.append("采购质保合同（MISSING）")

        # 3. 查批次故障率
        if request.batch_id:
            batch = self.conn.execute(
                "SELECT batch_id, part_no, supplier_id, total_units, failed_units, defect_rate FROM part_batches WHERE batch_id = ?",
                [request.batch_id],
            ).fetchone()
            if batch:
                evidence.append({
                    "source_class": "MOCK",
                    "source_ref": "demo.duckdb.after_sales.v1",
                    "rule_version": "batch.v1",
                    "content_summary": f"批次 {batch[0]}：{batch[4]}/{batch[3]} 故障（{batch[5]}）",
                })
                metrics.append(("批次故障率", f"{batch[5]}"))
            else:
                missing.append("批次追溯数据（MISSING）")
        else:
            # 查该供应商所有批次
            batches = self.conn.execute(
                "SELECT batch_id, total_units, failed_units, defect_rate FROM part_batches WHERE supplier_id = ?",
                [sid],
            ).fetchall()
            if batches:
                for b in batches:
                    evidence.append({
                        "source_class": "MOCK",
                        "source_ref": "demo.duckdb.after_sales.v1",
                        "rule_version": "batch.v1",
                        "content_summary": f"批次 {b[0]}：{b[2]}/{b[1]} 故障（{b[3]}）",
                    })
            else:
                missing.append("批次追溯数据（MISSING）")

        # 4. 查历史追偿
        recourse = self.conn.execute(
            "SELECT id, claim_id, amount, status, reason FROM supplier_recourse_claims WHERE supplier_id = ?",
            [sid],
        ).fetchall()
        if recourse:
            for r in recourse:
                evidence.append({
                    "source_class": "MOCK",
                    "source_ref": "demo.duckdb.after_sales.v1",
                    "rule_version": "recourse.v1",
                    "content_summary": f"历史追偿 {r[0]}：金额 {r[2]}，状态 {r[3]}，{r[4]}",
                })

        # 5. 结论
        review = bool(missing) or defect_rate > industry_avg
        conclusion_parts = []
        if contracts:
            active_contracts = [c for c in contracts if c[6] == "active"]
            if active_contracts:
                conclusion_parts.append(f"采购质保在期内（{len(active_contracts)} 份有效合同）")
            else:
                conclusion_parts.append("采购质保已过期，不可追偿")
        if defect_rate > industry_avg:
            conclusion_parts.append(f"不良率 {defect_rate} 超行业均值")
        if missing:
            conclusion_parts.append(f"缺少 {len(missing)} 项关键数据")

        conclusion = "；".join(conclusion_parts) + "。" if conclusion_parts else "数据不足。"
        if review:
            conclusion += " 候选追偿假设，缺少合同或批次追溯时禁止自动追偿，必须人工复核。"

        return self._build_outcome(conclusion, evidence, missing, metrics, review)

    def _build_outcome(self, conclusion, evidence, missing, metrics, review):
        """构造六段式输出结构（S8 供应商追偿）。"""
        return {
            "scenario": "S8",
            "conclusion": conclusion,
            "key_metrics": dict(metrics),
            "missing_items": missing,
            "manual_review_required": review,
            "evidence": evidence,
        }
