# 待人工评审

## HP-003：原文交付范围与售前售后全覆盖映射

- **触发**：`项目实战(1).md` 要求商品/客户/库存等电商示例；原冻结范围为售后 S1–S5。
- **需要确认**：两组完整演示是否采用 S1 电池诊断 + S2 索赔合规；若必须采用原文电商示例，需要新增独立切片，不得隐式扩 scope。
- **影响范围**：示例数据、黄金案例、skill 清单、验收截图和最终交付口径。
- **当前处理**：**已决策——售前售后全覆盖（10 场景）**。售前 5 场景（商机丢单/业绩未达标/客户流失/报价竞争力/线索质量）用瑞能真实 CRM 库；售后 5 场景（索赔合规/星级评定/电池包/供应商反向索赔/客户投诉）用固定 seed 模拟数据。PRD、数据模型、章程已同步；售前切片（S9）从 blocked 解锁，待 B1 门禁通过后实现。电商示例需求登记为备选扩展，不影响主交付口径。

## HP-004：S1 公共内核设计评审门禁

- **触发**：S0 已完成 uv 初始化、契约测试和 `/health` 运行验收；S1 公共内核仍受设计冻结约束。
- **需要确认**：G1 领域状态机、D4 数据库逻辑设计、D5 API 契约、D6 原型蓝图与 Slice 1 B1 是否通过评审；未通过前不得实现 Case 状态机、业务路由或持久化。
- **影响范围**：S1 的状态转换、幂等、取消、追问版本、Evidence 保留和 API 实现授权。
- **当前处理**：用户已明确本项目为实战演示，授权使用项目内 DuckDB 模拟数据库和可替换适配器；不连接真实生产系统。该授权不等同于真实生产验收，`FACT`/`MOCK`/`MISSING` 证据边界仍然有效。

### 当前例外与已批准能力

- 本项目允许本地 DuckDB fixture、固定模拟数据、可替换 RAG/NL2SQL 适配器和 Docker 学习运行骨架；这些都不得被描述为生产接入。售前真实数据源（瑞能 CRM SQLite 库）通过 DuckDB 只读 ATTACH 访问。
- S1 公共内核已实现并有本地契约测试；它是后续规格对齐的事实基线，不应再标记为"禁止新增 Case 状态机"。
- 售前 E1–E5 与售后 S1–S5 均为主交付范围；售前适配器是只读快照边界，不复制或导入 CRM 项目业务代码。
- 如无经授权的脱敏外部数据、认证边界与最小权限凭据，继续使用 `MOCK`/`MISSING`，不得创建真实连接。

## HP-005：生产可用版数据接入与认证授权

- **触发**：用户选择"生产可用版"；当前工程约束禁止连接真实生产系统，归因项目自身也未配置获授权的生产数据源、认证信任边界或密钥托管。
- **需要提供或书面确认**：
  1. 已脱敏且获授权的 DMS、CRM、手册/规则库只读接入方式，以及各来源的字段字典、数据拥有方和读取范围；
  2. 认证与授权契约：身份提供方、令牌验证方式、角色/租户/数据域的访问规则；
  3. 可定位且版本化的权威规则源：电池诊断、质保与重新授权、服务店星级、供应商合同与追偿；
  4. S3 的投诉、维修尝试、技师、SLA 数据契约，以及 S5 的合同、批次、追偿历史数据契约；
  5. 隔离的非生产验收环境与最小权限凭据。不得复用旧项目中发现的配置或凭据。
- **影响范围**：PostgreSQL 持久化、外部只读适配器、认证网关、业务规则启用、端到端验收与生产部署。
- **当前处理**：继续完成不依赖外部系统的生产准备工作；在上述资料和授权到位前，所有业务结论保持 `MOCK`/`MISSING` 并强制人工复核，不连接任何真实系统。

## HP-006：存储引擎选型修正（SQLite → DuckDB）

- **触发**：PRD 技术选型核对时用户提出"直接用 DuckDB 是不是会好点"；经实测验证（executed）：瑞能真实 CRM 库 `crm_database.db` 本身是 SQLite 格式，DuckDB 可直接 `ATTACH ... (TYPE sqlite, READ_ONLY)` 零 ETL 查询（31 张表、商机漏斗/流失视图实测通过）。
- **需要确认**：无（用户明确要求改用 DuckDB）。
- **影响范围**：存储引擎决策、PRD 12.1、03 技术方案选型表与架构图、00 章程、DATABASE_LOGICAL_DESIGN（D4）、AGENTS.md、DOCKER_RUNTIME、切片索引、依赖（+duckdb）、`infrastructure/database/`、NL2SQL 适配器、init 脚本、测试。
- **当前处理**：**已决策并完成迁移**——DuckDB 为当前演示/分析引擎（分析型负载列式执行 + ATTACH 瑞能库零 ETL + 零部署）；PostgreSQL 保留为生产目标（多人审计库），由 `validate_production_settings` 门禁保证（生产仍强制 PostgreSQL）。23/23 测试通过。

## HP-007：Docker Desktop 守护进程不可用，阻塞容器级运行验收

- **触发**：执行 `docker compose config --quiet` 已成功，默认核心服务清单为 `attribution-api` 与 `frontend`；随后读取服务状态时，Docker CLI 无法连接 `npipe:////./pipe/dockerDesktopLinuxEngine`。
- **需要提供或处理**：在本机启动 Docker Desktop 的 Linux 容器引擎，或提供可访问的等价 Docker daemon；之后重新执行 `docker compose --env-file .env.example up --build -d`、`docker compose ps` 与 `curl http://localhost:8002/health`。
- **影响范围**：核心层容器构建、服务启动、镜像内依赖解析，以及全部 `integrations` profile 的真实运行验证。
- **当前处理**：本机进程验证已完成：`uv run uvicorn attribution_analysis.app:app --host 127.0.0.1 --port 18002` 返回 `/health` 的 `{"status":"ok","service":"attribution-analysis"}`；核心健康/API/生产配置契约测试 **48 项全部通过（2026-08-17 更新：S0-S5 全部实现）**。这不能替代 Docker 容器级验收。

## HP-008：NL2SQL Embedding 模型挂载目录缺失

- **触发**：集成层前置核验已确认 RAG 源码、NL2SQL 源码、`bge-m3` 与 `bge-reranker-large` 目录存在；`.env.example` 指定的 `NL2SQL_EMBEDDING_MODEL_PATH=D:/ai_models/bge-large-zh-v1.5` 不存在，且模型根目录内未发现同名目录。
- **影响范围**：`embedding` 服务无法挂载模型，因而 `nl2sql` 依赖链、元数据构建及容器级只读验证均不可执行。
- **当前处理**：**已解决（2026-08-17）**。
  1. 模型实际存在于 `D:\heimaAI\PytorchSDXX\12_问数\代码\掌柜问数项目代码\data-agent\docker_windows\embedding\bge-large-zh-v1.5`（含 pytorch_model.bin 等完整文件，已通过目录核验）。
  2. `compose.yaml` 已简化，不再包含 `embedding`/`rag`/`nl2sql` 容器服务，因此该模型路径不再被归因系统的 Compose 引用。
  3. 后续如需启用 NL2SQL 集成层，可在本机 `.env` 中设置 `NL2SQL_EMBEDDING_MODEL_PATH` 指向上述已确认路径。

## HP-009：S9 售前切片 CRM 真实库路径缺失（2026-08-17 新增）

- **触发**：2026-08-17 S9 B1 评审准备过程中，尝试定位瑞能 CRM 真实库路径 `D:\heimaAI\PytorchSDXX\CRMProject_c\data\crm_database.db`，发现路径不存在。
- **影响范围**：S9 售前 5 场景（E1 商机丢单/E2 业绩未达标/E3 客户流失/E4 报价竞争力/E5 线索质量）无法实现，6 个白名单视图无法创建，4 个售前工具无法验证，黄金案例 G-E1-1～G-E5-1 无法执行。
- **当前处理**：**已解决（2026-08-17）**。
  1. CRM 数据库实际路径为 `D:\heimaAI\PytorchSDXX\CRMProject\CRMProject_c\data\crm_database.db`（7.67 MB，DuckDB ATTACH (TYPE sqlite, READ_ONLY) 实测通过）。
  2. 必需表已全部确认（executed）：`customers` 3665、`opportunities` 100、`contracts` 106、`sales_orders` 3359、`field_visits` 2643、`sales_persons` 74。
  3. S9 B1 门禁的数据库前置条件已满足，可以开始售前适配器实现。

## HP-010：真实 LLM、RAG 与业务 MySQL 接入配置

- **触发**：工作台已具备远程 LLM、RAG HTTP 和只读 MySQL 适配边界，但当前运行配置仍可处于显式 Demo 模式，未提供获授权的接入地址与最小权限凭据。
- **需要提供**：验收环境的 `ATTRIBUTION_LLM_*`、`ATTRIBUTION_RAG_*`、`ATTRIBUTION_NL2SQL_MODE=mysql`、`ATTRIBUTION_NL2SQL_DATABASE_URL`，以及仅具 SELECT 权限的 MySQL 账号与表/字段白名单。
- **当前处理**：Case 持久化、调用记录与失败透明化已在本地实现；缺配置或依赖失败必须作为失败 Execution 保留，禁止宣称真实数据或模型已成功调用。
