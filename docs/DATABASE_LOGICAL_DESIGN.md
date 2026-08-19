# 数据库逻辑设计与来源版本治理

> **状态**：draft / D4。仅定义逻辑模型与约束；本文不授权创建数据库、迁移、种子数据或真实数据连接。
>
> **上游来源**：`02_数据模型与黄金数据集.md`、`G1_领域模型、状态机与验收契约.md`、`ARCHITECTURE_AND_BEHAVIOR_BLUEPRINT.md`。
>
> **核心边界**：归因系统持久化自身任务、证据和结果；DMS、CRM、索赔单及业务单据只以带读取时刻的只读快照进入系统，绝不回写外部状态。

## 1. 物理存储选型决策

**决策**：正式运行环境采用 **PostgreSQL** 作为归因运行域、业务快照域、规则来源域和黄金数据元数据域的唯一关系型系统记录库。**DuckDB** 作为当前演示/分析引擎：本地固定 `seed=42` 的演示/测试 fixture，并可直接 ATTACH 瑞能真实 CRM SQLite 库实现售前零 ETL 查询；两者均不得保存多人共享 Case、证据、审计或规则版本。

| 评估维度 | SQLite（原默认） | DuckDB（演示/分析引擎） | PostgreSQL（生产目标） | 本系统结论 |
|---|---|---|---|---|
| 分析型负载（聚合/JOIN/漏斗/比率） | 行式 OLTP，聚合慢 | 列式 + 向量化执行，分析场景显著更快 | 可胜任但需服务部署 | DuckDB 最适合归因分析演示 |
| 并发 Case 与工具执行审计 | 单写者、文件锁会放大编排写冲突 | 单写多读，演示场景足够 | 事务并发与行级锁 | 多人审计必须 PostgreSQL |
| 售前真实数据（瑞能 CRM） | 需 ETL 导入 | **原生 ATTACH SQLite 库零 ETL** | 需导入迁移 | DuckDB 直接查瑞能库 |
| 不可变证据、状态迁移与版本 | 可实现但缺少服务端权限与治理边界 | 可实现，单文件便携 | 约束、事务、角色、审计与备份机制完备 | PostgreSQL 适合可追溯证据链 |
| JSON 快照、关系查询、全文检索 | 能力有限且扩展分散 | JSON 支持良好 | `JSONB`、索引、全文检索统一 | 适合快照和受控检索 |
| Agent 查询隔离 | 应用内自行约束，易泄露文件级权限 | 应用内约束（同 SQLite） | 独立只读角色、schema、视图和语句超时 | 适合最小权限适配器 |
| RAG 向量检索 | 无统一运行级治理 | 无（需扩展） | 可在获批 RAG 切片后评审启用 `pgvector` | 不在当前冻结期安装或启用 |
| 本地样例与离线测试 | 零配置、可随 fixture 提交 | 零配置、单文件、零部署 | 运维成本较高 | DuckDB 保留此用途并承担分析引擎 |

### 1.1 Agent 查询不是“让 Agent 连库”

```text
Agent / Planner
  → 工具注册表（场景、字段、最大行数、超时白名单）
    → 只读查询适配器（参数化查询 / 语义视图）
      → PostgreSQL 只读角色
        → 标准化快照 + 来源定位
```

Agent 只表达受控查询意图，不能持有连接串、数据库账号或任意 SQL 执行能力。适配器必须执行场景白名单、参数绑定、表/列允许集、行数上限、语句超时和读取审计；返回结果先成为 `business_snapshots`，再由证据服务写成 `Evidence`。NL2SQL 即使后续接入，也只能生成候选查询，由适配器验证后在只读角色下运行。

### 1.2 运行边界与后续启用条件

首期物理部署将至少隔离 `runtime`、`rules`、`golden` 三个 schema（或等价数据库边界），并为应用写入、查询适配器只读、运维迁移分别配置最小权限角色。外部 CRM/DMS 不迁入 PostgreSQL；它们保持只读适配器来源，读取结果以版本化快照进入本系统。

此项仅为架构决策，不改变当前设计冻结态。实际 PostgreSQL 实例、迁移工具、驱动、`pgvector` 扩展、连接配置和数据导入，均须等相应 Slice Spec 与测试计划获批后实施。

## 2. 分域与数据责任

```text
运行域：Conversation → AttributionCase → AnalysisPlan → ToolExecution
                                      └→ Evidence → AttributionResult

业务快照域：Case 关联 Snapshot（Claim / Fault / WorkOrder / Station ...）

规则与来源域：SourceAsset → SourceVersion → RuleDefinition → RuleVersion
                                      └→ Evidence / Result 引用

黄金数据域：GoldenDataset → GoldenCase → GoldenFixture / ExpectedAssertion
```

| 分域 | 保存内容 | 写入者 | 不可承担的职责 |
|---|---|---|---|
| 运行域 | 任务状态、计划、执行审计、证据、结果、追问版本 | Case 服务、编排器、证据服务、结果合成器 | 业务主数据的权威来源、外部单据状态 |
| 业务快照域 | 外部系统在特定读取时刻返回的标准化业务事实 | 只读适配器 | 回写 DMS/CRM、推导未经证实的规则 |
| 规则与来源域 | 制度文件、数据集、规则与版本、适用范围、来源等级 | 规则版本服务 | 把 `MOCK` 伪装成 `FACT` |
| 黄金数据域 | 固定样例、样例输入、预期断言、模拟资产版本 | 测试资产维护者 | 生产审计、真实业务事实 |

所有逻辑表都使用稳定的内部标识作为主键。外部标识（例如 `claim_id`、`wo_id`、VIN）只作为快照载荷中的业务键和索引候选，不能取代系统内部主键。

## 3. 运行域逻辑模型

### 3.1 会话、任务与幂等

| 实体 | 主键 | 最小字段 | 关系与约束 |
|---|---|---|---|
| `conversations` | `conversation_id` | `subject_id`、`summary_version`、`summary_text`、`last_active_at`、`created_at`、`updated_at` | 一个会话关联多个 Case；摘要只能递增版本 |
| `messages` | `message_id` | `conversation_id`、`case_id`、`role`、`content_ref`、`attachment_refs`、`created_at` | 只追加；保存用户/系统可见消息与已持久化进度摘要，不保存模型原始思维链 |
| `attachments` | `attachment_id` | `conversation_id`、`subject_id`、`object_key`、`content_type`、`size_bytes`、`parse_status`、`snapshot_id`、`created_at` | 对象存储引用不暴露物理路径；被 Evidence 引用后仅逻辑撤销 |
| `attribution_cases` | `case_id` | `conversation_id`、`scenario_code`、`question_text`、`input_fingerprint`、`idempotency_key`、`status`、`cancel_requested_at`、`cancel_reason`、`created_at`、`completed_at` | `conversation_id` 外键；`status` 为 G1 状态机枚举；未完成请求在 `(subject_id, conversation_id, input_fingerprint, idempotency_key)` 上唯一 |
| `case_state_transitions` | `transition_id` | `case_id`、`from_status`、`to_status`、`trigger_type`、`reason_code`、`occurred_at`、`actor_type` | 只追加；每次合法状态迁移有一条记录；拒绝的非法迁移另以 `rejection_reason` 记录 |

`attribution_cases` 是任务状态唯一拥有者。外部索赔状态、工单状态和授权申请状态不得写入该表的 `status` 字段。

### 3.2 计划、执行、证据与结果

| 实体 | 主键 | 最小字段 | 关系与约束 |
|---|---|---|---|
| `analysis_plans` | `plan_id` | `case_id`、`version_no`、`status`、`steps_snapshot`、`current_step_no`、`max_steps`、`created_at`、`superseded_at` | `(case_id, version_no)` 唯一；`max_steps=8`；追问或重规划只新增版本 |
| `tool_executions` | `execution_id` | `case_id`、`plan_id`、`step_no`、`tool_name`、`input_fingerprint`、`input_summary`、`status`、`attempt_no`、`started_at`、`finished_at`、`duration_ms`、`error_class`、`error_detail` | `case_id` 与 `plan_id` 外键；`(case_id, plan_id, step_no, tool_name, input_fingerprint)` 唯一；仅允许瞬时错误产生第 2 次尝试 |
| `evidence` | `evidence_id` | `case_id`、`execution_id`、`sequence_no`、`source_class`、`source_version_id`、`source_ref`、`rule_version_id`、`content_summary`、`raw_locator`、`payload_digest`、`confidence`、`recorded_at` | 只追加；`execution_id` 可为空，仅限人工补录并须记录 `recorded_by`；来源三元组均不可为空 |
| `attribution_results` | `result_id` | `case_id`、`version_no`、`status`、`six_part_content`、`key_metrics`、`missing_items`、`manual_review_required`、`based_on_evidence_digest`、`created_at` | `(case_id, version_no)` 唯一；只能新增修订版本；`based_on_evidence_digest` 固化所引用证据集合 |
| `result_evidence_refs` | `result_id + evidence_id` | `citation_order`、`usage_type`、`claim_fragment` | 显式实现 Result 到 Evidence 的多对多引用；无引用不得声称事实结论 |
| `reviews` | `review_id` | `case_id`、`result_id`、`status`、`reason_code`、`requested_by`、`assigned_to`、`created_at`、`completed_at` | Review 独立于 Case 生命周期；不覆盖 Result 或 Evidence |
| `review_actions` | `review_action_id` | `review_id`、`action_type`、`comment`、`evidence_id`、`actor_id`、`occurred_at` | 只追加；`confirm`、`reject`、`request_data`、`append_evidence` 均可审计 |
| `exports` | `export_id` | `case_id`、`result_version`、`format`、`object_key`、`status`、`created_by`、`expires_at`、`created_at` | 下载授权短期且绑定主体；产物保留来源等级和限制 |
| `event_outbox` | `event_id` | `subject_id`、`case_id`、`event_type`、`payload_ref`、`occurred_at`、`delivered_at` | 仅发布已持久化变化；作为 WebSocket 断线恢复游标来源 |

`evidence.sequence_no` 在同一 `case_id` 内单调递增，用于确定审计顺序。`payload_digest` 用于证明同一证据快照未被静默改写，不存储或输出不必要的原始敏感载荷。

## 4. 业务快照域

### 4.1 通用快照容器

| 实体 | 主键 | 最小字段 | 约束 |
|---|---|---|---|
| `business_snapshots` | `snapshot_id` | `case_id`、`snapshot_type`、`external_system`、`external_business_key`、`schema_version`、`captured_at`、`source_class`、`source_version_id`、`source_ref`、`normalized_payload`、`payload_digest` | 只追加；同一外部键的多次读取产生多个快照；`source_class` 只允许 `FACT`、`MOCK`、`MISSING` |
| `case_snapshot_refs` | `case_id + snapshot_id` | `purpose_code`、`attached_at` | Case 与多个快照关联；附件不改变快照内容 |

业务快照可由逻辑视图按 `snapshot_type` 解释为 `ClaimSnapshot`、故障案例、工单、车辆、服务站或维护记录；实现前不得据此创建物理分表。外部业务键允许重复，以保留不同读取时刻和来源版本。

### 4.2 `ClaimSnapshot` 最小载荷

`ClaimSnapshot` 载荷必须含：索赔单号、索赔状态、索赔类型、审核日期、审核明细、重新授权标志、授权申请状态、提交次数、退回日期、销毁通知标志、关联扣款单摘要、读取时刻与外部来源定位。

它只用于资格分析和证据引用，不能触发 DMS 写操作，也不能把外部索赔状态映射为归因 Case 状态。

### 4.3 场景边界

| 场景 | 已可建模的快照类型 | 当前限制 |
|---|---|---|
| S1 故障报修与维修诊断 | 车辆、工单、故障案例、诊断信号、维修尝试、批次/供应商摘要 | 电池健康字段可记录；阈值解释必须独立引用规则版本 |
| S2 索赔工单合规 | 索赔、工单、车辆、零件、保养、质保条款 | 重新授权只输出资格说明，不能代替审核 |
| S3 重复维修与投诉 | 投诉、维修尝试、技师画像、SLA 事件 | 规则与数据契约为 `MISSING`；禁止自动责任归因 |
| S4 服务网点/星级 | 服务站、评定检查项、稽查摘要 | 当前评分线和一票否决映射未逐项证实，按 `MOCK` 管理 |
| S5 其他售后运营/供应商追偿 | 供应商、批次、采购质保合同、追偿历史 | 关键合同、批次和责任比例数据为 `MISSING`；不得自动追偿 |

## 5. 规则、来源与版本域

### 5.1 版本链

| 实体 | 主键 | 最小字段 | 约束 |
|---|---|---|---|
| `source_assets` | `source_asset_id` | `source_name`、`source_kind`、`owner_scope`、`canonical_location`、`default_source_class` | 原始手册、DMS 说明、模拟数据集等来源资产；`default_source_class` 不能替代证据实际分类 |
| `source_versions` | `source_version_id` | `source_asset_id`、`version_label`、`content_digest`、`effective_from`、`effective_to`、`extracted_at`、`verification_status` | `(source_asset_id, version_label)` 唯一；版本失效不删除历史引用 |
| `rule_definitions` | `rule_id` | `rule_code`、`scenario_code`、`rule_name`、`decision_scope` | 只定义规则身份；`decision_scope` 限制为“解释/建议/人工复核”，不允许“自动处置” |
| `rule_versions` | `rule_version_id` | `rule_id`、`version_label`、`source_class`、`source_version_id`、`applicability`、`condition_expression`、`outcome_semantics`、`effective_from`、`effective_to`、`review_status` | `(rule_id, version_label)` 唯一；任何版本均明确来源等级和适用范围 |
| `rule_evidence_refs` | `rule_version_id + source_version_id + locator` | `quoted_excerpt_digest`、`interpretation_note` | 一条规则可引用多个来源章节；定位不可省略 |

### 5.2 来源等级不变量

1. `evidence.source_class`、`business_snapshots.source_class` 与 `rule_versions.source_class` 必须显式填写，禁止默认值。
2. `FACT` 必须引用已验证的 `source_versions` 和可定位 `source_ref`；缺其中任一项，写为 `MISSING`，不能降格伪装为 `FACT`。
3. `MOCK` 必须关联固定样例或演示资产版本；其 `applicability` 限制于测试、演示或候选假设。
4. `MISSING` 仍须创建来源记录，`source_ref` 填写“缺失项标识/预期提供方”，`rule_version_id` 使用声明该缺口的版本；它不是空值。
5. 若结果涉及关键责任、审批、拒赔、扣款、降级或追偿，且引用集合含 `MISSING` 或仅以 `MOCK` 支撑，则 `manual_review_required=true`，且结果状态不得表达自动裁决。

## 6. 黄金数据域与模拟资产隔离

| 实体 | 主键 | 最小字段 | 约束 |
|---|---|---|---|
| `golden_datasets` | `dataset_id` | `dataset_name`、`dataset_version`、`seed`、`source_class`、`purpose`、`created_at` | `(dataset_name, dataset_version)` 唯一；首期模拟数据固定 `seed=42` |
| `golden_cases` | `golden_case_id` | `dataset_id`、`case_code`、`scenario_code`、`input_description`、`fixture_ref`、`expected_outcome` | `(dataset_id, case_code)` 唯一；与生产 `case_id` 无外键关系 |
| `golden_assertions` | `assertion_id` | `golden_case_id`、`assertion_type`、`expected_value`、`source_class_expectation`、`manual_review_expectation` | 覆盖来源等级、人工复核、禁止处置、状态与引用证据 |

黄金样例和演示数据不得进入运行域的生产审计语义：同一物理存储实现时必须有独立命名空间或明确 `dataset_id` 隔离，禁止让模拟 VIN、索赔单或阈值混入真实快照查询结果。

## 7. 审计、删除与索引候选

### 7.1 审计字段与保留规则

所有可写运行、规则与黄金数据实体均保留 `created_at`、`created_by`、`updated_at`、`updated_by`；证据、状态迁移、工具执行和结果版本额外要求 `recorded_at` 或 `occurred_at`。历史证据、执行记录、状态迁移、结果版本、来源版本和规则版本**禁止就地更新或物理删除**。

允许纠错的方式是：新增修订版本、增加撤销标记及撤销原因，并保持原记录可审计。业务快照的保留期限须在数据合规评审中补充；在此之前不得自行设定清理任务。

### 7.2 索引候选

| 访问目标 | 候选索引 | 目的 |
|---|---|---|
| 会话下查看 Case 时间线 | `attribution_cases(conversation_id, created_at)` | 工作台历史与追问定位 |
| 幂等复用 | 未完成 Case 的 `subject_id, conversation_id, input_fingerprint, idempotency_key` | 阻断重复执行 |
| Case 审计回放 | `case_state_transitions(case_id, occurred_at)`、`tool_executions(case_id, started_at)`、`evidence(case_id, sequence_no)` | 复原过程与证据顺序 |
| 版本结果读取 | `attribution_results(case_id, version_no)` | 追问后的历史版本对比 |
| 外部快照查询 | `business_snapshots(external_system, external_business_key, captured_at)` | 查找并保留读取时刻差异 |
| 规则/来源定位 | `rule_versions(rule_id, version_label)`、`source_versions(source_asset_id, version_label)` | 精确定位依据 |

## 8. 状态持久化与失败恢复

```text
创建/复用 Case
  → 写入 Case + created → validating 的状态迁移
  → 新建 Plan(vN)
  → 每个步骤先写 ToolExecution，再调用只读适配器
  → 工具响应合格时追加 Evidence；失败时更新该执行终态并记录错误
  → 追加 Result(vN) 与 Result-Evidence 引用
  → 追加最终状态迁移
```

取消、超时和失败不能删除任何已有 Evidence。追问通过新增 `AnalysisPlan.version_no` 和 `AttributionResult.version_no` 恢复，并重用既有证据引用；不得复制、覆盖或重新标注历史证据。

## 10. 基础设施数据主人矩阵

| 组件 | 唯一职责 | 保存内容 | 不承担的职责 | 启用状态 |
|---|---|---|---|---|
| PostgreSQL | 归因系统记录库 | runtime/rules/golden schema、审计、版本、事件外箱 | 外部 CRM/DMS 主数据 | 正式运行目标 |
| MySQL | 学习环境业务查询库 | 固定种子售前/售后业务视图与 NL2SQL 演示数据 | Case、审计、规则版本的系统记录 | 模拟环境 |
| MinIO | 二进制对象存储 | 附件、解析产物、导出文件 | 业务元数据、权限决定 | 学习环境 |
| Milvus | 旧 RAG 项目检索索引 | RAG 文档向量 | 归因 Evidence 或规则版本记录 | 旧项目适配依赖 |
| Qdrant | 旧 NL2SQL 元数据检索 | 表/字段/纠错向量 | 通用 RAG 正式向量库 | 旧项目适配依赖 |
| Elasticsearch | NL2SQL 字段值全文检索 | 查询辅助索引 | 审计或 Result 主存储 | 可选学习依赖 |
| MongoDB | 旧 RAG 原始载荷/会话依赖 | 旧 RAG 所需非结构化数据 | 归因 Case 的权威审计 | 旧项目适配依赖 |
| DuckDB | 本地演示/分析引擎 | 固定 `seed` 本地测试/演示数据；ATTACH 瑞能 CRM SQLite 库只读查询 | 多人运行、共享审计或正式存储 | 当前演示引擎 |
| SQLite | 瑞能 CRM 真实数据源（只读 ATTACH） | 售前场景真实业务数据（customers/opportunities/contracts 等 31 表） | 写入、权限决定 | 外部只读来源 |

**约束**：Milvus、Qdrant、pgvector 的职责不得重叠。当前学习环境保留前两者以复用旧项目，pgvector 仅作为 PostgreSQL 学习切片，未经独立检索契约和运行验收不得作为第二个生产检索主人。

## 11. D4 评审准出清单

- [ ] 任一 `AttributionResult` 都能追溯至其 `Evidence`、规则版本、来源版本与外部快照读取时刻。
- [ ] `FACT`、`MOCK`、`MISSING` 在规则、快照、证据和黄金数据中均有不可省略的显式字段。
- [ ] `MISSING` 或仅 `MOCK` 的关键判断可持久化人工复核与待补项，不能产生自动处置。
- [ ] 取消、失败、超时和追问不会删除或覆盖已记录的证据与结果版本。
- [ ] S3、S5 的缺失数据契约已作为阻塞项建模，未伪造成可实施的业务 schema。
- [ ] 已确认归因系统对 DMS/CRM 保持只读，任务状态与外部单据状态完全分离。
