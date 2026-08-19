"""CRM 适配器兼容入口（拆分后保留原导入路径）。

原 demo.py 已拆分为两个独立模块：
- adapters/crm/readonly.py       → CrmReadonlyAdapter / CrmSchemaError（真实库 FACT 证据）
- adapters/crm/demo_adapter.py   → DemoCrmAdapter（固定 seed 模拟库 MOCK 证据）

此处仅做 re-export，新代码请直接导入上述两个模块。
"""
from attribution_analysis.adapters.crm.demo_adapter import (
    REFERENCE_DATE,
    MOCK_RULE_VERSION,
    MOCK_SOURCE_CLASS,
    MOCK_SOURCE_REF,
    DemoCrmAdapter,
)
from attribution_analysis.adapters.crm.readonly import (
    CRM_DB_PATH,
    RULE_VERSION,
    SOURCE_CLASS,
    SOURCE_REF,
    CrmReadonlyAdapter,
    CrmSchemaError,
)

__all__ = [
    "CRM_DB_PATH",
    "CrmReadonlyAdapter",
    "CrmSchemaError",
    "DemoCrmAdapter",
    "REFERENCE_DATE",
    "RULE_VERSION",
    "SOURCE_CLASS",
    "SOURCE_REF",
    "MOCK_RULE_VERSION",
    "MOCK_SOURCE_CLASS",
    "MOCK_SOURCE_REF",
]