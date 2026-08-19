# Attribution Analysis

经营归因分析系统的独立工程。它把售后与售前经营异常组织为“输入 → 证据 → 受控结论”的可追溯流程。

# 当前交付边界

- Slice 0：FastAPI 健康检查与工程基线。
- Slice 1：公共 Case → Plan → ToolExecution → Evidence → Result 内核。
- Slice 2：本项目内 SQLite 模拟数据库、固定白名单证据查询，以及 RAG/NL2SQL 可替换适配器。
- 旧项目只作为适配器实现参考：知识库入口为 `app/api/http/query_server.py`，问数入口为 `main.py`；不得把旧项目内部模块导入本项目领域层。
- 模拟数据和 `MOCK` 证据只服务于可复现实战演示，不能表述为生产接入或真实制度结论。

## 目录职责

```text
src/attribution_analysis/
├── domain/             # 状态机和 Evidence 等稳定领域模型
├── application/        # 用例编排；tools 统一收集外部证据
├── api/                # FastAPI 路由与 HTTP 序列化
├── ports/              # RAG/NL2SQL 等能力契约
├── adapters/           # 旧项目或本地 Demo 的端口实现
├── infrastructure/     # SQLite 生命周期、仓储和未来持久化实现
└── config/             # 环境变量与运行配置
scripts/init_demo_db.py # 初始化项目内模拟数据库
 data/                  # 本地运行产物，不提交数据库文件
```

## 本地运行

```bash
uv sync --extra dev
uv run python scripts/init_demo_db.py
uv run pytest
uv run uvicorn attribution_analysis.app:app --reload
```

`data/attribution_demo.db` 是模拟业务库；适配器默认只读，NL2SQL 不接受任意 SQL。真实旧项目接入时，只需在 `adapters/` 增加实现并保持 `ports/` 契约，不复制旧项目业务代码。

## Docker 完整学习环境

完整运行环境由 [`docs/DOCKER_RUNTIME.md`](docs/DOCKER_RUNTIME.md) 定义。`compose.yaml` 同时编排归因后端与前端、PostgreSQL + pgvector、MySQL、MongoDB、MinIO、Milvus、Qdrant、Elasticsearch、Embedding，以及复用旧项目源码运行的 RAG 和 NL2SQL 服务。

SQLite 只保留为测试和离线最小样例；Docker 环境下的服务职责和启动顺序以该文档为准。
