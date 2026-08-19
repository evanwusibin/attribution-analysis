# ADR-001 · 存储引擎从 DuckDB 迁移到 MySQL

> **状态**：accepted（2026-08-17）
> **影响范围**：基础设施层、全部适配器、数据初始化脚本
> **逆转成本**：中（需重写适配器 SQL）

## 背景

项目最初选择 DuckDB 作为演示/分析引擎（`03_技术方案与架构.md`），原因是 DuckDB 可直接 ATTACH SQLite 并零 ETL 读取瑞能 CRM 库。随着开发推进出现三个问题：

1. **文件锁**：DuckDB 单文件在 Windows 上被进程占用后报 `IOException`，多测试并发时不稳定
2. **真实数据接入受阻**：瑞能 CRM 数据需要迁移到 MySQL（Docker 中已运行 mysql:8.0 服务）
3. **企业级部署需要**：MySQL 是团队已有运维基线，DuckDB 是单机嵌入式

## 决策

统一使用 MySQL（Docker 容器 `mysql:8.0`，端口 3307）作为唯一数据源：

- 售后 10 表 → `attribution` 库
- 售前模拟 7 表 → `attribution` 库
- 瑞能真实 CRM 8 表 → `attribution` 库（`crm_*` 前缀）
- S6/S7/S8 新表 → `attribution` 库
- 认证表 → `attribution` 库

新增 `MySQLConnection` 包装器（`infrastructure/database/duckdb.py`），提供与 DuckDB 兼容的 `execute()/fetchall()/fetchone()/executemany()` 接口，适配器无需改写即可切换。

## 后果

### 正面
- 消除文件锁问题，测试稳定（86/86 通过）
- 真实 CRM 数据统一管理，可通过 SQL 直接分析
- 与团队 MySQL 运维基线一致

### 负面
- DuckDB 的零 ETL ATTACH SQLite 能力不再使用（但 `crm_database.db` 已迁移）
- `MySQLConnection._sql()` 需要做 `?` → `%s` 占位符转换
- MySQL 要求 `VARCHAR` 带长度、`BOOLEAN` 用 `TINYINT`，建表 DDL 与 DuckDB 差异

## 备选方案

- **保留 DuckDB + MySQL 双引擎**：复杂度高，不必要的抽象
- **直接使用 SQLite**：数据量大时性能不足，且文件锁问题相同