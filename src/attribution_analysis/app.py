"""应用入口。

组合根保持极薄，具体路由装配由 API 应用工厂负责。
"""

from attribution_analysis.api.app import create_app


app = create_app()
