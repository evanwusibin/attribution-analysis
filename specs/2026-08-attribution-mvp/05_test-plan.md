# 05 Test Plan

## S0 契约

| 契约 | 给定 | 期望 | 测试位置 |
|---|---|---|---|
| 服务就绪 | 应用已加载 | `GET /health` 返回 200 与固定载荷 | `tests/test_health.py` |
| 工程隔离 | 源码依赖图 | 无 `CRMProject_c` 内部导入 | 代码审查门禁 |

## 质量门禁

```text
pip install -e ".[dev]"
pytest
```

后续每个业务规则必须有至少一个正例、反例和证据不足例；测试名称必须描述其保护的业务契约。
