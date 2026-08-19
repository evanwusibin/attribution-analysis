# Agent 协作约束

## 读取顺序

1. `docs/DESIGN_DELIVERY_BLUEPRINT.md`
2. `CONTEXT.md`
3. 当前 Slice Spec
4. `docs/api/`、`docs/prototype/` 与后续 `docs/data/` 契约
5. 对应测试

## 强制不变量

- 证据必须标识 `FACT`、`MOCK` 或 `MISSING`，并带来源定位。
- `MISSING` 或仅依赖 `MOCK` 的关键结论只能要求人工复核，不能自动审批、扣款、降级或追偿。
- 工具层默认只读；外部能力必须通过适配器接入，不得直接导入 `CRMProject_c` 内部模块。
- 每个切片必须先有可执行测试与 Spec，再写业务实现。

## 当前边界

- Slice 0 仅允许健康检查和可复现测试；其运行验收证据仍待记录。
- Slice 1 及之后已由项目负责人授权进入实战开发：本项目允许创建本地 DuckDB 模拟数据库和适配器测试，但禁止连接真实生产系统。
- RAG/NL2SQL 必须通过 `ports/` 契约接入；旧项目实现放在 `adapters/`，不得向领域层扩散外部依赖。
