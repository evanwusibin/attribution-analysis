"""外部知识与数据能力的稳定端口。"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RetrievalHit:
    title: str
    content: str
    source_ref: str
    score: float
    source_class: str = "MOCK"


@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: tuple[dict, ...]
    sql: str
    source_ref: str
    source_class: str = "MOCK"
    params: tuple[object, ...] = ()


@dataclass(frozen=True)
class KnowledgeImportTask:
    task_id: str
    status: str
    done_list: tuple[str, ...] = ()
    running_list: tuple[str, ...] = ()


class RAGPort(Protocol):
    def retrieve(self, query: str, limit: int = 5) -> tuple[RetrievalHit, ...]:
        """按查询检索知识库文档，返回按相关度排序的命中。"""
        ...


class KnowledgeImportPort(Protocol):
    def import_documents(self, files: tuple[tuple[str, str, bytes], ...]) -> tuple[KnowledgeImportTask, ...]:
        """提交文件到外部知识库导入流程。"""
        ...

    def import_status(self, task_id: str) -> KnowledgeImportTask:
        """读取外部知识库导入任务状态。"""
        ...


class NL2SQLPort(Protocol):
    def query(self, question: str) -> QueryResult:
        """把自然语言问题映射为白名单 SQL 并返回结构化结果。"""
        ...
