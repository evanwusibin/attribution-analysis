"""将 Docker 环境变量渲染为问数项目真正读取的 YAML。"""
from os import environ
from pathlib import Path


TARGET = Path("/runtime/conf/app_config.yaml")


def main() -> None:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        f"""logging:
  file: {{enable: true, level: INFO, path: logs, rotation: 10 MB, retention: 7 days}}
  console: {{enable: true, level: INFO}}
db_meta: {{host: mysql, port: 3306, user: attribution, password: {environ['MYSQL_PASSWORD']}, database: attribution_meta}}
db_dw: {{host: mysql, port: 3306, user: attribution, password: {environ['MYSQL_PASSWORD']}, database: attribution_business}}
qdrant: {{host: qdrant, port: 6333, embedding_size: 1024}}
embedding: {{host: embedding, port: 80, model: {environ.get('NL2SQL_EMBEDDING_MODEL_ID', 'BAAI/bge-large-zh-v1.5')}}}
es: {{host: elasticsearch, port: 9200, index_name: data-agent-column}}
llm: {{model_name: {environ['NL2SQL_LLM_MODEL']}, api_key: {environ['NL2SQL_LLM_API_KEY']}, base_url: {environ['NL2SQL_LLM_BASE_URL']}}}
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
