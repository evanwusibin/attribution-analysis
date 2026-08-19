from attribution_analysis.adapters.nl2sql.demo import DemoNL2SQLAdapter
from attribution_analysis.adapters.rag.demo import DemoRAGAdapter
from attribution_analysis.application.core import CoreService, CreateCaseCommand
from attribution_analysis.application.tools.evidence import EvidenceToolset
from attribution_analysis.infrastructure.database.duckdb import open_database
from attribution_analysis.infrastructure.database.runtime import PersistentCaseStore


def test_case_snapshot_survives_a_new_service_instance(tmp_path) -> None:
    """Contract: a completed Case and its evidence remain readable after service reconstruction."""
    database = open_database(tmp_path / "runtime.duckdb")
    service = CoreService(
        EvidenceToolset(DemoRAGAdapter(), DemoNL2SQLAdapter(database)),
        store=PersistentCaseStore(database),
    )
    created, reused = service.create_case(
        CreateCaseCommand("subject", "conversation", "分析订单延迟原因", "persist-key")
    )

    recovered = CoreService(
        EvidenceToolset(DemoRAGAdapter(), DemoNL2SQLAdapter(database)),
        store=PersistentCaseStore(database),
    ).get_case(created.case_id, "subject")

    assert reused is False
    assert recovered.case_id == created.case_id
    assert len(recovered.plans) == 1
    assert len(recovered.evidence) == 2
    assert len(recovered.results) == 1
