# Attribution Analysis · 经营归因分析系统

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://github.com/evanwusibin/attribution-analysis/actions/workflows/tests.yml/badge.svg)](https://github.com/evanwusibin/attribution-analysis/actions/workflows/tests.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green)](src/attribution_analysis/api)
[![Docker](https://img.shields.io/badge/docker-compose-ready-blue)](compose.yaml)

经营归因分析系统的独立工程。它把售后与售前经营异常组织为“输入 → 证据 → 受控结论”的可追溯流程，输出六段式结论 + `FACT`/`MOCK`/`MISSING` 三色证据 + 人工复核边界。

> **前端**：`5173` 归因工作台（`auth` 轮播 `public/images/1.mp4` + 白字首屏，已去储能图，`36px` 标题）

## 当前交付边界

- **Slice 0**：FastAPI 健康检查与工程基线
- **Slice 1**：公共 Case → Plan → ToolExecution → Evidence → Result 内核
- **Slice 2**：SQLite 模拟库、固定白名单证据查询、RAG/NL2SQL 可替换适配器
- **S3-S5**：售后底座 + 故障诊断 + 索赔合规（含 `FACT` 引用）
- **S9**：售前适配器（漏斗/流失/报价/线索）
- 旧项目只作为适配器参考（`app/api/http/query_server.py` / `main.py`），不得向领域层扩散

## 技术栈

- **后端**：FastAPI + DuckDB（演示）/ PostgreSQL + pgvector（生产）+ SQLAlchemy
- **前端**：原生 HTML/CSS/JS + 轮播（`1.mp4` + 3 图）、`auth` 白字首屏
- **AI**：RAG（Milvus）+ NL2SQL（`12_问数`）+ 13 业务工具（9 售后 + 4 售前）
- **部署**：Docker Compose（`compose.yaml` 编排 9 服务：后/前端、pgvector、MySQL、Mongo、MinIO、Milvus、Qdrant、ES、Embedding）

## 目录职责

```
src/attribution_analysis/
├── domain/             # 状态机和 Evidence 等稳定领域模型
├── application/        # 用例编排；tools 统一收集外部证据
├── api/                # FastAPI 路由与 HTTP 序列化
├── ports/              # RAG/NL2SQL 等能力契约
├── adapters/           # 旧项目或本地 Demo 的端口实现
├── infrastructure/     # SQLite 生命周期、仓储和未来持久化实现
└── config/             # 环境变量与运行配置
frontend/               # 轮播登录 + 工作台（5173）
public/images/          # 1.mp4, 2.webp, 3-4.png
compose.yaml            # 一键编排
```

## 快速开始

### 本地开发

```bash
uv sync --extra dev
uv run python scripts/init_demo_db.py
uv run pytest  # 117 项契约测试
uv run uvicorn attribution_analysis.app:app --reload  # http://127.0.0.1:8000
```

### Docker 一键启动

```bash
# 依赖宿主 MySQL:3307 / Qdrant:6333 / ES:9200 / Embedding:8081 已运行
docker compose up -d  # 前端 http://127.0.0.1:5173 后端 http://127.0.0.1:8002

# 账号 analyst/analyst123 admin/admin123
curl -X POST http://127.0.0.1:8002/api/v1/auth/login \
  -H "Content-Type: application/json" -d '{"username":"analyst","password":"analyst123"}' -c /tmp/cookies.txt
curl -b /tmp/cookies.txt -X POST http://127.0.0.1:8002/api/v1/after-sales/diagnostics \
  -H "Content-Type: application/json" -d '{"question":"电池包SOC异常，SOH只有70%","vin":"LSGAB52R7DF000005"}'
```

`data/attribution_demo.db` 为模拟库；适配器只读，NL2SQL 不接受任意 SQL。

## 复习指南

完整项目复习见 [复习指南.md](复习指南.md)（六层架构/三色证据/13 工具/六段输出/Docker/面试高频问答）

## 许可证

MIT — 见 [LICENSE](LICENSE)
