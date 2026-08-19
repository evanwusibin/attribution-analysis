"""S7 服务店星级评定归因服务。"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class StarEvaluationRequest:
    question: str
    station_code: str | None = None


STAR_KEYWORDS = ("星级", "评定", "评分", "降级", "4S店", "服务店", "检查项")


class StarEvaluationService:
    """S7 服务店运营与星级归因执行服务。"""

    def __init__(self, connection) -> None:
        """绑定演示数据库连接。"""
        self.conn = connection

    def is_star_scenario(self, question: str) -> bool:
        """判断问题是否属于星级评定场景。"""
        return any(kw in question for kw in STAR_KEYWORDS)

    def run(self, request: StarEvaluationRequest) -> dict:
        """执行星级评估：读取检查项 → 一票否决判定 → 总分计算。"""
        station_code = request.station_code or ""
        evidence: list[dict[str, object]] = []
        missing: list[str] = []
        metrics: list[tuple[str, str]] = []

        # 查所有店或指定店
        if station_code:
            stations = self.conn.execute(
                "SELECT station_code, station_name, current_star, discount_coefficient, region FROM service_stations WHERE station_code = ?",
                [station_code],
            ).fetchall()
        else:
            stations = self.conn.execute(
                "SELECT station_code, station_name, current_star, discount_coefficient, region FROM service_stations",
                [],
            ).fetchall()

        if not stations:
            missing.append("服务店数据（MISSING）")
            return self._build_outcome("未找到服务店数据", [], missing, metrics, True)

        veto_items: list[str] = []
        total_score = 0
        max_score = 0

        for s in stations:
            scode, sname, star, coeff, region = s[0], s[1], s[2], s[3], s[4]
            evidence.append({
                "source_class": "MOCK",
                "source_ref": "demo.duckdb.after_sales.v1",
                "rule_version": "star.v1",
                "content_summary": f"服务店 {sname}（{scode}）：当前 {star}，折让系数 {coeff}",
            })
            metrics.append(("当前星级", star or "—"))

            # 查检查项
            items = self.conn.execute(
                "SELECT item_code, item_name, required_star, max_score, actual_score, is_veto, issue_desc, category FROM star_evaluation_items WHERE station_code = ?",
                [scode],
            ).fetchall()

            for item in items:
                icode, iname, rstar, mscore, ascore, veto, idesc, cat = item
                total_score += ascore or 0
                max_score += mscore or 0
                if veto and ascore < mscore:
                    veto_items.append(f"{iname}（一票否决）")
                    evidence.append({
                        "source_class": "MOCK",
                        "source_ref": "demo.duckdb.after_sales.v1",
                        "rule_version": "star.v1",
                        "content_summary": f"一票否决项：{iname} - {idesc or '不达标'}",
                    })
                elif ascore < mscore:
                    evidence.append({
                        "source_class": "MOCK",
                        "source_ref": "demo.duckdb.after_sales.v1",
                        "rule_version": "star.v1",
                        "content_summary": f"扣分项：{iname}（{cat}）得分 {ascore}/{mscore} - {idesc or '未达标'}",
                    })

        if max_score > 0:
            metrics.append(("总分", f"{total_score}/{max_score}"))

        # 结论
        review = bool(veto_items) or bool(missing)
        if veto_items:
            conclusion = f"一票否决项触发：{', '.join(veto_items)}。建议降级，不论总分。阈值标记为 MOCK，不自动降级。"
        elif max_score > 0:
            pct = round(total_score / max_score * 100, 1)
            conclusion = f"总分 {total_score}/{max_score}（{pct}%）。星级评估完成，建议人工确认是否升降级。"
        else:
            conclusion = "数据不足，无法完成星级评估。"
            missing.append("检查项得分（MISSING）")

        return self._build_outcome(conclusion, evidence, missing, metrics, review)

    def _build_outcome(self, conclusion, evidence, missing, metrics, review):
        """构造六段式输出结构（S7 星级评定）。"""
        return {
            "scenario": "S7",
            "conclusion": conclusion,
            "key_metrics": dict(metrics),
            "missing_items": missing,
            "manual_review_required": review,
            "evidence": evidence,
        }
