# 经营归因业务切片 Spec 索引与批准门禁

> **状态**：draft。本文替代旧函数级 Spec 的施工地位；旧文件仅供历史对照。
>
> **当前实现说明**：S1 本地公共内核已按用户明确指令实现并完成契约验证；本文的设计评审状态仍保持 `draft`，不代表真实 PostgreSQL、外部工具或业务场景已获批。

## 1. 统一 B1 批准门禁

| 门禁 | 必须证据 | 未满足时的结果 |
|---|---|---|
| 范围 | 目标、非目标、依赖和外部边界明确 | 保持 `draft` |
| 数据/规则 | 每个输入与规则标注 `FACT`、`MOCK` 或 `MISSING`，并有版本与来源 | 不得实现或自动裁决 |
| 状态/接口 | 状态迁移、幂等、取消、失败语义均映射 API 与画板 | 不得新增业务路由 |
| 测试 | 正常、失败、取消、幂等与来源等级的可失败契约测试 | 不得开始最小实现 |
| 验收 | 运行证据格式、黄金输入与预期输出可复现 | 不得标记 `accepted` |

## 2. 切片主线

| 切片 | 状态 | 目标与非目标 | 依赖 | 黄金案例与强制失败测试 | 进入 B1 的剩余项 |
|---|---|---|---|---|---|
| S1 公共内核 | draft | **目标**：Case、Plan、Execution、Evidence、Result 的状态与版本。**非目标**：具体业务规则、真实 DB/工具。 | Slice 0 | G-A-5 缺失证据；重复幂等；取消后证据保留；单工具超时 | G1、API、原型评审结论 |
| S2 只读证据工具 | draft | **目标**：工具白名单、只读适配器、来源标准化与失败降级。**非目标**：任意 SQL、外部写操作。 | S1 | 无来源响应拒绝为可信 Evidence；超时不阻塞独立工具 | 适配器最小权限与查询允许集 |
| S3 售后共享底座 | draft | **目标**：版本化模拟快照、VIN/工单/索赔/零件关联。**非目标**：真实 DMS/CRM 连接。 | S2 | `seed=42` 可复现；FACT/MOCK 隔离；外部键不同读取时刻共存 | Snapshot 字段级数据契约 |
| S4 故障报修与维修诊断（电池包为首域） | draft | **目标**：业务场景路由 → 故障域识别 → 诊断路径执行 → 候选根因；电池包是首个完整诊断域。**非目标**：自动拒赔、供应商追偿。 | S3 | 正常、异常、证据不足、反例；SOH 阈值仅 MOCK 时必须人工复核 | 电池诊断路径评审 |
| S5 S2 索赔合规 | draft | **目标**：质保、延保、原厂件、保养、换表与重新授权资格。**非目标**：审批/回写 DMS。 | S3、S4 | G-A-1、G-A-5、G-A-7；超保、非原厂、换表叠加 | FACT 规则定位逐条复核 |
| S9 售前 CRM 适配 | draft | **目标**：5 个售前场景（E1 商机丢单/E2 业绩/E3 流失/E4 报价/E5 线索）经 CRM 只读适配器复用同一归因内核。**非目标**：写 CRM、任意 SQL、自动处置。 | S1、S2 | G-E1-1～G-E5-1；竞品价 `MISSING` 降级；无来源响应拒绝为可信 Evidence | 售前工具注册表评审、适配器白名单视图逐视图核对 |
| S10 平台能力 | draft | **目标**：loguru 运行日志、WebSocket 8 种实时消息、附件管理、配置热更新、会话级联删除、历史消息与继续追问（先行）；认证中心授权登录（延后阶段）。**非目标**：业务归因规则、复杂多租户/RBAC。 | Slice 0、S1 | 非法 token 拒绝（延后）；WS 断连后任务可恢复；级联删除三目录清理；非法配置回滚保留上一份；日志脱敏 | 日志选型已定 loguru；认证回调流程评审（延后）、WS 消息时序契约 |

## 3. 各 Slice 的施工契约

### Slice 1：归因公共内核

- **领域对象**：`Conversation`、`AttributionCase`、`AnalysisPlan`、`ToolExecution`、`Evidence`、`AttributionResult`。
- **状态变化**：仅接受 G1 所列迁移；任何非法迁移记录拒绝原因；追问创建 Plan/Result 新版本。
- **数据接缝**：运行域 PostgreSQL 逻辑模型（生产目标）；当前演示/分析引擎为 DuckDB（`infrastructure/database/duckdb.py`，可直接 ATTACH 瑞能 CRM SQLite 库），不接入生产物理库或迁移。
- **失败/降级**：输入少于 5 字拒绝；单工具 10 秒、整案 30 秒；取消在工具边界生效。
- **验收**：同幂等键只得到一个 Case 和一个执行审计；取消后 Evidence 可读取；无 Evidence 不产生事实性 Result。

### Slice 2：统一只读证据工具

- **领域对象**：`ToolExecution`、`BusinessSnapshot`、`Evidence`、`SourceVersion`。
- **接口接缝**：只接受受控查询意图；结果由读取 API 返回，禁止对外暴露任意 SQL 或工具调度 API。
- **失败/降级**：工具响应无 `source_class/source_ref/rule_version` 时不能写可信 Evidence；瞬时失败仅重试一次；独立失败进入部分成功或待补充。
- **验收**：只读角色、参数绑定、行数/超时限制均有测试；`MISSING` 生成补数任务而非空白结论。

### Slice 3：售后共享证据底座

- **领域对象**：业务快照、来源版本、规则版本、黄金数据集。
- **数据接缝**：仅导入固定 `seed=42` 的模拟样例；外部业务标识作为快照载荷，不是归因系统主键。
- **失败/降级**：来源不明的快照强制降为 `MISSING`；模拟数据不能混入 FACT 查询视图。
- **验收**：同一 VIN/索赔外部键的不同读取时刻可并存；从 Evidence 可回溯到快照与来源版本。

### Slice 4：S1 电池包故障诊断

- **领域对象**：`FaultCase`、`FaultDomain`、`DiagnosticPlaybook`、`DiagnosticSignal`、`RootCauseHypothesis`。
- **数据接缝**：SOH、SOC、循环次数、容量、衰减率、批次和供应商均以快照/证据进入；阈值解释独立引用 RuleVersion。
- **失败/降级**：诊断报告、检测方法或 FACT 条款缺失时进入 `needs_input`，不输出自然衰减、拒赔或追偿裁决。
- **验收**：G-A-5 与 G-C-1 必须输出候选假设、缺失清单和人工复核；反例证明“异常数值”不会自动处置。

### Slice 5：S2 索赔工单合规

- **领域对象**：`ClaimSnapshot`、工单/车辆/零件/保养快照、质保 RuleVersion。
- **数据接缝**：T5 质保保养与重新授权规则为 FACT；原始定位必须进入 Evidence；DMS 只读。
- **失败/降级**：关键信息缺失或仅 MOCK 支撑时输出待补充；资格判断与最终审核严格分离。
- **验收**：G-A-1 给出建议而非审批；G-A-5 强制人工复核；G-A-7 超一年拒绝“创建资格”建议但绝不回写 DMS。

### Slice 10：平台能力（认证+实时+文件+管理）

- **领域对象**：`AuthSession`、`Conversation`（含状态机）、`Attachment`、`TaskLog`、`SystemConfig`、WebSocket 消息信封。
- **状态变化**：会话 active/archived/deleted；任务 queued/running/success/failed/cancelled；附件 parsing/ready/failed；非法迁移记录拒绝原因。
- **数据接缝**：认证走授权登录（入口页→回调页→访问令牌换取），前端不落明文 token；文件按 `uploads/{user_id}/{conversation_id}/`、`exports/...`、`workspace/...` 隔离，路径穿越校验；配置热更新失败回滚保留上一份有效配置。
- **失败/降级**：非法/过期 websocket_token 拒绝连接；WS 断连后任务状态通过 `GET /api/tasks/{task_id}` 恢复；日志含敏感信息脱敏，管理员不得查看其他用户会话明文。
- **验收**：认证登录后可进工作台；8 种实时消息按契约时序推送；级联删除同步清理三目录；配置重载即时生效；历史消息查询与切换旧会话追问可复现。

## 4. 阻塞切片登记

| 切片 | 状态 | 阻塞数据契约 | 允许的当前产出 |
|---|---|---|---|
| S6 重复维修与投诉 | ✅ implemented（2026-08-17 本地实现，Spec 见 [`S6_重复维修与投诉.md`](S6_重复维修与投诉.md)） | — | complaints/repair_attempts/technician_profiles/service_sla_events 已建表 |
| S7 服务店与星级 | ✅ implemented（2026-08-17 本地实现，Spec 见 [`S7_服务店星级.md`](S7_服务店星级.md)） | — | service_stations/star_evaluation_items 已建表，阈值 MOCK |
| S8 供应商追偿 | ✅ implemented（2026-08-17 本地实现，Spec 见 [`S8_供应商追偿.md`](S8_供应商追偿.md)） | — | supplier_warranty_contracts/supplier_recourse_claims 已建表 |
| S9 售前 CRM 适配 | draft（2026-08 解锁） | ~~CRM 数据访问授权、只读适配器允许集、场景黄金集~~ → 已由 `03_技术方案与架构.md` 第七节提供：6 个白名单语义视图、4 个售前工具、G-E1-1～G-E5-1 黄金集、只读快照边界 | 售前工具注册表评审与白名单视图逐视图核对 |

## 5. 批准记录

| 切片 | B1 设计评审 | 测试计划 | 实现授权 | 验收状态 |
|---|---|---|---|---|
| S1 公共内核 | 本地授权（用户明确指令） | `tests/test_core_api.py` 等，20 项 | ✅ 本地仅限 | ✅ implemented |
| S2 只读证据工具 | 本地授权 | `tests/test_s2_integrations.py`，2 项 | ✅ 本地仅限 | ✅ implemented（本地契约） |
| S3 售后共享证据底座 | 本地授权（设计依据：`02_数据模型` 一.1 + specs §3 Slice 3） | `tests/test_s3_after_sales.py`，5 项 | ✅ 本地仅限 | ✅ implemented（seed=42 可复现、FACT/MOCK 隔离、来源回溯、无自由 SQL） |
| S4 故障报修与维修诊断（电池包为首域） | 本地授权（设计依据：`02_数据模型` 一.4 + specs §3 Slice 4） | `tests/test_s4_fault_diagnosis.py`，8 项 | ✅ 本地仅限 | ✅ implemented（G-C-1 候选假设+MISSING+人工复核；SOH 异常不自动处置；未知域转人工） |
| S5 索赔合规 | 本地授权（设计依据：`02_数据模型` 一.1 + G-A-1/G-A-7） | `tests/test_s5_claim_compliance.py`，10 项 | ✅ 本地仅限 | ✅ implemented（质保规则 FACT 可追溯；输出建议非审批；重新授权 5 条件校验） |
| Slice 6–8 | 数据契约阻塞 | 禁止创建 | 禁止 | 未开始 |
| Slice 9 | 售前设计已入 `03_技术方案与架构.md` 第七节，本地模拟授权 | `tests/test_s9_presales.py`，11 项 | ✅ 本地仅限 | ✅ implemented（G-E1-1～G-E5-1 全通；竞品 MISSING 降级；未知域转人工） |
| Slice 10 | 平台能力需求已入 PRD FR-01/FR-14～FR-21，待 B1 门禁评审 | 禁止创建（待门禁通过） | 仍禁止（待门禁通过） | 未开始 |

### 2026-08-17 售后切片解锁（S3/S4 本地实现）

> **变更类型**：业务实现推进。用户明确指示"主要是业务点实现出来，按你认为最合理的方式"，据此将售后首个业务场景（S3 底座 + S4 故障诊断）从 `draft` 推进到本地实现。
>
> **授权边界**：与 S1 相同，仅限本地 DuckDB 模拟数据与适配器测试；不连接真实 DMS/CRM、不写入生产系统、不做自动拒赔/追偿/归责。

| 切片 | B1 设计评审 | 测试计划 | 实现授权 | 验收状态 |
|---|---|---|---|---|
| S3 售后共享证据底座 | 本地授权（设计依据：`02_数据模型` 一.1 + specs §3 Slice 3） | `tests/test_s3_after_sales.py` 已创建并运行验证（5 项） | ✅ 本地仅限 | ✅ implemented（seed=42 可复现、FACT/MOCK 隔离、来源回溯、无自由 SQL） |
| S4 故障报修与维修诊断（电池包为首域） | 本地授权（设计依据：`02_数据模型` 一.4 + specs §3 Slice 4） | `tests/test_s4_fault_diagnosis.py` 已创建并运行验证（8 项） | ✅ 本地仅限 | ✅ implemented（G-C-1 候选假设+MISSING+人工复核；SOH 异常不自动处置；未知域转人工） |

**回写**：本文状态、`specs/README.md` 索引、顶层 `README.md` 当前状态均已同步；实现细节见 `src/attribution_analysis/{ports,adapters,domain,application}/` 与 `api/after_sales.py`。

### 2026-08-17 售前切片解锁（S9 本地实现）

> **变更类型**：业务实现推进。用户确认售前模拟黄金数据集方案后，按"真正吃透痛点"的要求，将售前 5 场景（E1 商机丢单/E2 业绩未达标/E3 客户流失/E4 报价竞争力/E5 线索质量）从 `draft` 推进到本地实现。
>
> **授权边界**：与 S1/S3/S4 相同，仅限本地 DuckDB 模拟数据与适配器测试；不连接真实 CRM、不写入生产系统、不做自动处置。

| 切片 | B1 设计评审 | 测试计划 | 实现授权 | 验收状态 |
|---|---|---|---|---|
| S9 售前模拟黄金数据集 | 本地授权（设计依据：`02_数据模型` 一.3 + `03_技术方案` 第七节 + G-E1-1～G-E5-1） | `tests/test_s9_presales.py` 已创建并运行验证（11 项） | ✅ 本地仅限 | ✅ implemented（G-E1-1 关键人+报价偏高；G-E2-1 华东 45% 达成率；G-E3-1 流失 high；G-E4-1 偏离度分析；G-E5-1 广告转化率；竞品 MISSING 降级；未知域转人工；短问题 422） |

**回写**：本文状态、`specs/README.md` 索引、顶层 `README.md` 当前状态均已同步；实现细节见 `src/attribution_analysis/{ports,crm,adapters/crm,application/tools/presales,application/scenarios/presales,api/presales}/` 与 `tests/test_s9_presales.py`。

### 2026-08-17 真实 CRM 数据接入（售前场景升级）

> **变更类型**：数据源升级。用户提供 `D:\heimaAI\PytorchSDXX\CRMProject\CRMProject_c\data\crm_database.db`（7.3 MB 瑞能真实库），已确认数据量：customers 3,665 / contacts 1,903 / opportunities 100 / contracts 106 / sales_orders 3,359 / field_visits 2,643 / sales_persons 74 / sales_targets 36。
>
> **执行**：
> 1. `scripts/migrate_crm_to_mysql.py` 将 8 张核心表迁入 MySQL `attribution` 库（`crm_*` 前缀）；
> 2. 新增 `adapters/crm/mysql.py` `MysqlCrmAdapter`（6 视图 + 4 工具，全部 FACT）；
> 3. 售前 API 切换到真实数据；数据库统一为 MySQL（`ATTRIBUTION_DATABASE_URL=mysql://...`）；
> 4. 识别并适配脱敏数据口径：外键（owner_id/visitor_id/opportunity_id）被清空、时间维度错位（订单 2025/目标 2026）、`first_deal_date` 清空但 `deal_status` 可用——业绩按部门聚合、成交判断改用 `deal_status`、订单时间改用 `created_at`。

| 场景 | 真实数据验证结果 |
|---|---|
| E1 商机丢单 | ✅ 100 商机阶段分布可查（项目立项 72 / 输单 1 / 赢单 1 等），候选假设生成 |
| E2 业绩未达标 | ✅ 74 人按部门聚合（战略业务部签约 527 亿最大），达成率对比 |
| E3 客户流失 | ✅ 真实客户流失评分（跟进递减 + 拜访缺失 + 未成交 → high） |
| E5 线索质量 | ✅ 8 个来源真实转化率（自行开发 34% / 公司分配 46% / 展会开拓 4%） |

**回写**：本记录、顶层 `README.md` 数据源说明；真实数据改造后全套 72 项测试通过。

### 2026-08-17 前端三场景支持 + 基础设施收尾

> **变更类型**：前端同步 + 基础设施修复。用户指示"要的都需要的"，补齐前端场景入口与运行环境问题。

| 项 | 内容 |
|---|---|
| 前端场景入口 | `frontend/` 增加场景联动：E1-E5（售前）/ S1（售后诊断）/ S2（索赔合规）/ 通用归因，按场景渲染参数表单（VIN/批次/索赔单号/商机ID/区域/来源）并调用对应 API |
| 前端六段渲染 | 候选结论 / 关键指标 / 证据链（FACT/MOCK/MISSING 着色）/ 缺失清单 / 人工复核提示完整展示 |
| 容器连通 | `compose.yaml` API 数据源改为 `mysql://...@host.docker.internal:3307/attribution`（容器内经 Dock 网络访问宿主 MySQL） |
| 静态挂载修复 | `api/app.py` 前端目录挂载改为可选（API 容器不再依赖前端文件） |
| 真实数据口径 | `MysqlCrmAdapter` 适配脱敏数据：业绩按部门聚合、成交用 `deal_status`、订单时间用 `created_at`、拜访 `LIKE %拜访%` |

**浏览器端到端验证（Playwright）**：登录 → E1 商机丢单（真实数据 + MISSING 降级）→ S1 电池包 SOH=70%（FACT 缺失 → 人工复核）→ S2 索赔 CL-001（建议赔付 + FACT 证据链 + 置信度 100%）全部通过。
