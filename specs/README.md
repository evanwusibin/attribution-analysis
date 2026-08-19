# 首期 Spec 索引

设计交付链、权威来源与切片门禁见 [`../docs/DESIGN_DELIVERY_BLUEPRINT.md`](../docs/DESIGN_DELIVERY_BLUEPRINT.md)。

| 文档 | 作用 | 状态 |
|---|---|---|
| `01_brief.md` | 范围与成功条件 | approved for Slice 0 |
| `02_requirements.md` | 可验证需求与失败路径 | approved for Slice 0 |
| `03_design.md` | 模块边界与状态约束 | approved for Slice 0 |
| `04_tasks.md` | 切片任务与依赖 | active |
| `05_test-plan.md` | 契约测试与质量门禁 | approved for Slice 0 |
| `06_acceptance.md` | 运行后填写的证据记录 | completed for Slice 0 |
| `07_release.md` | 上线、监控和回滚计划 | active（本地演示 MVP 边界） |
| `08_retrospective.md` | 复盘和改进行动 | active |

业务切片必须在对应条目由 `draft` 进入 `approved` 后才能实现。

## 新版业务切片（S3/S4 已本地实现）

| 文档 | 作用 | 状态 |
|---|---|---|
| [`2026-08-business-slices/README.md`](2026-08-business-slices/README.md) | Slice 1–10 范围、依赖、B1 门禁与阻塞登记 | draft（S3/S4 本地实现已授权） |
| [`2026-08-business-slices/TEST_PLAN.md`](2026-08-business-slices/TEST_PLAN.md) | Slice 1–5、10 契约测试计划 | draft |
| [`2026-08-business-slices/S10_平台能力.md`](2026-08-business-slices/S10_平台能力.md) | 平台能力切片（认证/WS/附件/配置/日志/级联删除）Spec | draft |

2026-08-17：S3（售后共享证据底座）与 S4（故障报修与维修诊断，电池包为首域）按用户指示完成本地实现，测试见 `tests/test_s3_after_sales.py` 与 `tests/test_s4_fault_diagnosis.py`（合计 37 项通过）。S9（售前模拟黄金数据集）按用户确认的方案完成本地实现，测试见 `tests/test_s9_presales.py`（11 项通过）。其余切片仍须由 `draft` 进入 `approved` 后才能实现。

该目录不替代 Slice 0，也不授权任何业务实现。
