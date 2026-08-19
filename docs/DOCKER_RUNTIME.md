# Docker 化分层运行环境

> **状态**：Compose 配置展开已验证；默认层仅启动 `frontend` 与 `attribution-api`，用于验收当前内存公共内核。集成层通过 `integrations` profile 显式启用。RAG、NL2SQL 和全服务启动仍待独立执行验证，不能将本手册解读为这些服务已可运行。
>
> 运行职责、外部能力边界和分层启动顺序以 `docs/INTEGRATION_AND_RUNTIME_SPEC.md` 为准。

## 服务拓扑

```text
frontend → attribution-api → PostgreSQL + MySQL + MongoDB
                          → rag-query → Milvus + MongoDB + MinIO + DashScope MCP
                          → nl2sql → MySQL + Qdrant + Elasticsearch + Embedding
rag-import → Milvus + MongoDB + MinIO + MinerU
PostgreSQL + pgvector：运行态关系数据与 pgvector 学习切片
Milvus：RAG 项目的向量检索实现
Qdrant：NL2SQL 元数据和纠错向量检索实现
DuckDB：本地演示/分析引擎，单文件零部署；可 ATTACH 瑞能 CRM SQLite 库只读查询
```

| 服务 | 来源与职责 | 主机端口 |
|---|---|---|
| `attribution-api` | 本项目 FastAPI | 8002 |
| `frontend` | 本项目演示前端 | 5173 |
| `postgres` | 归因运行数据、pgvector | 5432 |
| `mysql` | 模拟业务数据与 NL2SQL 数据仓库 | 3307 |
| `mongo` | RAG 会话与原始载荷 | 27017 |
| `minio` | RAG 文档和图片对象存储 | 9000、9001 |
| `milvus` + `etcd` | RAG 向量检索 | 19530、9091 |
| `qdrant` | NL2SQL 元数据向量检索 | 6333、6334 |
| `elasticsearch` | NL2SQL 字段值全文检索 | 9200 |
| `embedding` | NL2SQL embedding 推理 | 8081 |
| `rag-import` / `rag-query` | 复用知识库项目的导入、查询入口 | 8010、8011 |
| `nl2sql` | 复用问数项目的查询入口 | 8012 |

## 启动层级

| 层级 | 命令 | 范围与验收目的 |
|---|---|---|
| 核心层（默认） | `docker compose up --build -d` | 启动工作台与归因 API；不拉起存储、中间件、模型或旧项目。当前 API 仍是内存公共内核。 |
| 集成层 | `docker compose --profile integrations up --build -d` | 额外启动 PostgreSQL、MySQL、MongoDB、MinIO、向量库、检索与旧 RAG/NL2SQL 入口；仅在路径、模型与密钥前置条件满足后使用。 |

环境变量分为两个作用域：

- **Compose 插值作用域**：命令必须显式传入 `--env-file .env.example`，以填充镜像标签、数据库密码和宿主机挂载路径等 `${…}`。Compose 不会从服务的 `env_file` 读取这些插值变量。
- **容器进程作用域**：服务依次读取 `.env.example` 和可选 `.env`。`.env` 中的同名值覆盖模板；真实密钥只能放入忽略的 `.env`，不能写回模板。

## 首次启动

1. 如需覆盖模型路径或密钥，复制环境模板并填写本机 `.env`。仅运行核心层时，此步骤可跳过。

```bash
copy .env.example .env
```

2. 默认启动核心层。干净克隆必须显式声明模板作为 Compose 插值来源。

```bash
docker compose --env-file .env.example up --build -d
```

3. 核心健康检查。

```bash
curl http://localhost:8002/health
```

4. 需要复用 RAG/NL2SQL 时，再确保以下路径存在：`RAG_SOURCE_PATH`、`NL2SQL_SOURCE_PATH`、三个模型路径；并启用集成层。

```bash
docker compose --env-file .env.example --profile integrations up --build -d
```

5. 初始化 NL2SQL 元数据。MySQL 启动时已创建 `attribution_business` 演示数仓和 `attribution_meta` 元数据表；旧项目的构建脚本会读取前者并填充后者、Qdrant 与 Elasticsearch。

```bash
docker compose exec nl2sql uv run python -m app.scripts.build_meta_knowledge -c conf/meta_config.yaml
```

5. 通过 `rag-import` 上传知识文档后，RAG 查询服务才会自动创建和填充 Milvus 集合。

## MCP 边界

旧知识库项目使用 DashScope 的 Streamable HTTP MCP WebSearch 服务。它不是旧项目内的本地 MCP Server，因此不虚构一个空容器；`rag-query` 从 `.env` 读取 `MCP_DASHSCOPE_BASE_URL` 和 `OPENAI_API_KEY` 后直接调用该服务。后续本地 MCP 工具应以独立容器加入，并由归因 API 经端口契约调用。

## 已知前置条件

- `rag-import` 依赖 MinerU SaaS 的有效令牌；未配置时，查询链路之外的文档导入不可用。
- `rag-query` 和 `nl2sql` 是把旧项目源码挂载入容器运行的复用方式，不复制旧业务代码。
- 首次镜像构建和模型加载耗时较长；模型由宿主机挂载，避免在 Compose 内重复下载。
