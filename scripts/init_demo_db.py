"""将本项目模拟业务数据初始化到 data/。"""
from attribution_analysis.config.settings import settings
from attribution_analysis.infrastructure.database.duckdb import open_database


def main() -> None:
    path = settings.database_url.removeprefix("duckdb:///")
    connection = open_database(path)
    connection.close()
    print(f"initialized demo database: {path}")


if __name__ == "__main__":
    main()
