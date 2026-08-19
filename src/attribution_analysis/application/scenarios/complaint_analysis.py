"""S6 重复维修与客户投诉归因诊断服务。

业务场景路由 → 查询重复维修记录 → 投诉记录 → 技师画像 → SLA 事件 → 候选归因。
阈值标记 MOCK，缺失数据标记 MISSING，不自动归责。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ComplaintAnalysisRequest:
    question: str
    vin: str | None = None
    complaint_id: str | None = None
    wo_id: str | None = None


COMPLAINT_KEYWORDS = ("投诉", "重复维修", "没修好", "修了", "态度差", "服务差", "多次", "复发")


class ComplaintAnalysisService:
    """S6 重复维修与客户投诉归因执行服务。"""

    def __init__(self, connection) -> None:
        """绑定演示数据库连接。"""
        self.conn = connection

    def is_complaint_scenario(self, question: str) -> bool:
        """判断问题是否属于投诉/重复维修场景。"""
        return any(kw in question for kw in COMPLAINT_KEYWORDS)

    def run(self, request: ComplaintAnalysisRequest) -> dict:
        """执行诊断，返回六段结构。"""
        vin = request.vin or ""
        evidence: list[dict[str, object]] = []
        missing: list[str] = []
        metrics: list[tuple[str, str]] = []

        # 1. 查重复维修
        recurring = self.conn.execute(
            "SELECT vin, fault_code, COUNT(*) as cnt FROM repair_attempts WHERE vin = ? GROUP BY vin, fault_code HAVING cnt >= 2",
            [vin],
        ).fetchall() if vin else self.conn.execute(
            "SELECT vin, fault_code, COUNT(*) as cnt FROM repair_attempts WHERE is_recurring = 1 GROUP BY vin, fault_code",
            [],
        ).fetchall()

        if recurring:
            for r in recurring:
                evidence.append({
                    "source_class": "MOCK",
                    "source_ref": "demo.duckdb.after_sales.v1",
                    "rule_version": "repair.v1",
                    "content_summary": f"VIN {r[0]} 故障码 {r[1]} 重复维修 {r[2]} 次",
                })
            metrics.append(("重复维修次数", f"{recurring[0][2]} 次"))
        else:
            missing.append("重复维修记录（MISSING）")

        # 2. 查投诉记录
        complaints = self.conn.execute(
            "SELECT id, complaint_type, complaint_content, severity FROM complaints WHERE vin = ?",
            [vin],
        ).fetchall() if vin else self.conn.execute(
            "SELECT id, complaint_type, complaint_content, severity FROM complaints LIMIT 5",
            [],
        ).fetchall()

        if complaints:
            for c in complaints:
                evidence.append({
                    "source_class": "MOCK",
                    "source_ref": "demo.duckdb.after_sales.v1",
                    "rule_version": "complaint.v1",
                    "content_summary": f"投诉 {c[0]}：{c[1]} - {c[2]}（严重度：{c[3]}）",
                })
            metrics.append(("投诉数", f"{len(complaints)} 条"))
        else:
            missing.append("投诉记录（MISSING）")

        # 3. 查技师画像
        tech_id = self.conn.execute(
            "SELECT tech_id FROM repair_attempts WHERE vin = ? LIMIT 1", [vin],
        ).fetchone() if vin else None

        if tech_id and tech_id[0]:
            tech = self.conn.execute(
                "SELECT tech_id, name, specialty, total_repairs, successful_repairs, avg_repair_time_hours, certification_level FROM technician_profiles WHERE tech_id = ?",
                [tech_id[0]],
            ).fetchone()
            if tech:
                success_rate = round(tech[4] / max(tech[3], 1) * 100, 1) if tech[3] else 0
                evidence.append({
                    "source_class": "MOCK",
                    "source_ref": "demo.duckdb.after_sales.v1",
                    "rule_version": "tech.v1",
                    "content_summary": f"技师 {tech[1]}（{tech[6]}）：总维修 {tech[3]} 次，成功率 {success_rate}%，平均工时 {tech[5]}h",
                })
                metrics.append(("技师成功率", f"{success_rate}%"))
                if success_rate < 80:
                    evidence.append({
                        "source_class": "MOCK",
                        "source_ref": "demo.duckdb.after_sales.v1",
                        "rule_version": "tech.v1",
                        "content_summary": f"技师成功率 {success_rate}% 低于 80% 阈值（MOCK），疑似技能不足",
                    })

        # 4. 查 SLA 违规
        wo_id = request.wo_id or (self.conn.execute(
            "SELECT wo_id FROM repair_attempts WHERE vin = ? LIMIT 1", [vin],
        ).fetchone()[0] if vin else None)

        if wo_id:
            sla_events = self.conn.execute(
                "SELECT event_type, delay_hours, is_overdue FROM service_sla_events WHERE wo_id = ? AND is_overdue = 1",
                [wo_id],
            ).fetchall()
            if sla_events:
                for s in sla_events:
                    evidence.append({
                        "source_class": "MOCK",
                        "source_ref": "demo.duckdb.after_sales.v1",
                        "rule_version": "sla.v1",
                        "content_summary": f"SLA 违规：{s[0]} 延迟 {s[1]} 小时",
                    })
                metrics.append(("SLA 违规", f"{len(sla_events)} 次"))
            else:
                metrics.append(("SLA 违规", "0 次"))

        # 5. 结论
        review = bool(missing) or bool(recurring)
        conclusion_parts = []
        if recurring:
            conclusion_parts.append("重复维修归因：同一故障多次维修未解决")
        if complaints:
            conclusion_parts.append("客户投诉已记录")
        if tech_id and tech_id[0]:
            conclusion_parts.append("技师技能评估完成")
        if sla_events:
            conclusion_parts.append("SLA 时效违规")

        conclusion = "；".join(conclusion_parts) + "。" if conclusion_parts else "数据不足，无法形成归因结论。"
        if review:
            conclusion += " 证据等级为 MOCK，必须人工复核，不自动归责。"

        return {
            "scenario": "S6",
            "conclusion": conclusion,
            "key_metrics": dict(metrics),
            "missing_items": missing,
            "manual_review_required": review,
            "evidence": evidence,
        }
