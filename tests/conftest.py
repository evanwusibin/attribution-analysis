"""测试进程必须与开发服务器使用不同的可写运行库。"""

import os

os.environ["ATTRIBUTION_ENV"] = "test"
os.environ["ATTRIBUTION_DATABASE_URL"] = "duckdb:///:memory:"
os.environ["ATTRIBUTION_RUNTIME_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ATTRIBUTION_AUTH_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ATTRIBUTION_NL2SQL_MODE"] = "demo"
os.environ["ATTRIBUTION_RAG_MODE"] = "demo"
os.environ["ATTRIBUTION_LLM_MODE"] = "demo"
