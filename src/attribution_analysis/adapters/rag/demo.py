"""本地 RAG 适配器；仅用于演示，不伪装成真实制度知识。"""
from attribution_analysis.ports.evidence import RAGPort, RetrievalHit


class DemoRAGAdapter(RAGPort):
    def __init__(self, documents: tuple[RetrievalHit, ...] | None = None) -> None:
        """绑定演示文档集（缺省为内置两条规则文档）。"""
        self.documents = documents or (
            RetrievalHit("履约规则", "订单承诺日期与实际签收日期的差值用于判断交付延迟。", "demo.manual.delivery.v1", 0.98),
            RetrievalHit("库存规则", "可用库存低于订单需求时，订单可能进入缺货等待。", "demo.manual.inventory.v1", 0.91),
        )

    def retrieve(self, query: str, limit: int = 5) -> tuple[RetrievalHit, ...]:
        """按词项命中排序返回最相关文档（演示评分）。"""
        terms = set(query.replace("，", " ").split())
        ranked = sorted(self.documents, key=lambda item: sum(term in item.content for term in terms), reverse=True)
        return tuple(ranked[:limit])
