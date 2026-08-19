# 06 Acceptance Evidence

> 仅记录已执行命令与实际结果；不要预填通过结论。

## S0

- 执行日期：2026-03-14
- Python 版本：由 `uv` 项目环境解析并执行
- 安装命令：`uv sync --extra dev`
- 安装结果：生成 `uv.lock`，项目开发环境可用
- 测试命令：`uv run pytest`
- 测试结果：`2 passed`（存在 1 条 FastAPI/Starlette 依赖弃用警告，不影响当前契约）
- 健康检查命令：`uv run python -c "from fastapi.testclient import TestClient; from attribution_analysis.app import app; response=TestClient(app).get('/health'); print(response.status_code); print(response.json())"`
- 健康检查响应：HTTP `200`，`{'status': 'ok', 'service': 'attribution-analysis'}`
- 当前结论：S0 工程基线已具备可复现安装、测试和健康检查证据；S1 公共内核已在用户明确授权下实现并完成本地契约验证。

## S1 公共内核

- 实现范围：Case 生命周期、合法状态迁移审计、Plan 版本、ToolExecution、Evidence、Result、幂等复用、追问、取消、证据与结果查询。
- 存储边界：当前使用进程内运行域存储，仅用于本地可复现验证；未创建 PostgreSQL、迁移或真实业务连接。
- 来源边界：当前演示证据显式标记为 `MOCK`，结论强制 `manual_review_required=true`；未接入 FACT 业务数据。
- 测试命令：`uv run pytest`
- 测试结果：`20 passed`（存在 1 条 FastAPI/Starlette 依赖弃用警告，不影响当前契约）
- 静态检查命令：`uv run python -m compileall -q src tests`
- 静态检查结果：通过
- 健康检查命令：`uv run python -c "from fastapi.testclient import TestClient; from attribution_analysis.app import app; response = TestClient(app).get('/health'); assert response.status_code == 200; assert response.json() == {'status': 'ok', 'service': 'attribution-analysis'}; print(response.json())"`
- 健康检查响应：HTTP `200`，`{'status': 'ok', 'service': 'attribution-analysis'}`
- 当前结论：S1 公共内核达到 `implemented`，S2 的本地受控适配器契约已验证；业务执行流、持久化和业务切片仍受 `HP-005` 的生产接入授权与数据契约门禁约束，不得据此宣称完整业务项目验收。

## S5 索赔合规切片（2026-08-17 实现）

- 实现范围：质保资格判断、延保校验、原厂件校验、保养记录校验、重新授权资格评估（G-A-1/G-A-3/G-A-4/G-A-7）。
- 存储边界：使用 Demo 适配器 MOCK 数据（CL-001～CL-007）；质保规则基于 T5 手册（FACT）；延保、保养记录为 MOCK。
- 来源边界：质保手册规则标记为 FACT（`比亚迪混动轻卡T5保修保养手册_T45C10__docx.txt`）；重新授权规则标记为 FACT（`reauthorize_v1.0.docx.txt`）。
- 测试命令：`uv run pytest tests/test_s5_claim_compliance.py -v`
- 测试结果：`10 passed`，覆盖 G-A-1（保内+原厂件+按时保养）、G-A-2（延保覆盖）、G-A-3（超保拒赔）、G-A-4（非原厂件拒赔）、G-A-7（重新授权资格校验）。
- 验收证据：
  - 质保规则可追溯（source_class=FACT，source_ref=手册章节）
  - 输出建议而非审批（recommendation 不含"已批准/已拒绝"）
  - 重新授权需满足 5 个条件（状态/类型/期限/无重复/销毁通知）
- 当前结论：S5 索赔合规达到 `implemented`，覆盖质保资格判断与重新授权资格；只输出建议与证据链，不执行自动审批/拒赔/回写 DMS。

## P2 认证边界

- 实现范围：本地环境仅允许显式 `X-Subject-Id` 测试主体；非本地环境强制 Bearer Token，拒绝把请求头或原始 Token 直接当作主体。
- 测试命令：`uv run pytest tests/test_authentication.py -q --tb=short`
- 测试结果：`3 passed`；完整回归为 `20 passed`。
- 当前结论：生产令牌验证器、身份提供方和 PostgreSQL 运行域均等待 `HP-005` 的隔离环境与接入授权；当前实现不接受未验证身份。
