"""MySQLConnection 断线自动重连契约测试。

契约：MySQL 服务重启/空闲超时导致连接失效后，下一次 execute/executemany
必须自动重建连接并成功，而不是让全局单例连接永久 500。
用 mock 模拟底层连接失效，不依赖真实 MySQL 实例。
"""
from unittest.mock import MagicMock, patch

import pymysql
import pytest

from attribution_analysis.infrastructure.database.duckdb import MySQLConnection


class _FakeDeadConnection:
    """首次调用抛连接失效异常，重连后返回的新连接正常。"""

    def __init__(self, error_class, fail_times: int = 1):
        self.error_class = error_class
        self.fail_times = fail_times
        self.executed = 0

    def cursor(self):
        self.executed += 1
        if self.executed <= self.fail_times:
            raise self.error_class(0, "")
        return MagicMock()


def test_execute_reconnects_after_interface_error() -> None:
    """InterfaceError（socket 已关闭）时 execute 自动重连并成功。"""
    conn = MySQLConnection(_FakeDeadConnection(pymysql.err.InterfaceError), url="mysql://u:p@h/db")
    with patch(
        "attribution_analysis.infrastructure.database.duckdb.open_mysql",
        return_value=MySQLConnection(MagicMock()),
    ):
        result = conn.execute("SELECT 1")
    assert result is not None
    assert conn._conn is not None


class _FakeServerGoneConn:
    """模拟 MySQL 2006 server gone away（OperationalError 带 errno）。"""

    def __init__(self):
        self.executed = 0

    def cursor(self):
        self.executed += 1
        if self.executed == 1:
            raise pymysql.err.OperationalError(2006, "MySQL server has gone away")
        return MagicMock()


def test_execute_reconnects_on_2006_server_gone_away() -> None:
    """真实 server gone away（errno=2006）自动重连并成功。"""
    conn = MySQLConnection(_FakeServerGoneConn(), url="mysql://u:p@h/db")
    with patch(
        "attribution_analysis.infrastructure.database.duckdb.open_mysql",
        return_value=MySQLConnection(MagicMock()),
    ):
        result = conn.execute("SELECT 1")
    assert result is not None


def test_executemany_reconnects_and_commits() -> None:
    """executemany 连接失效时自动重连并提交事务。"""
    conn = MySQLConnection(_FakeDeadConnection(pymysql.err.InterfaceError), url="mysql://u:p@h/db")
    with patch(
        "attribution_analysis.infrastructure.database.duckdb.open_mysql",
        return_value=MySQLConnection(MagicMock()),
    ):
        conn.executemany("INSERT INTO t VALUES (%s)", [("a",)])
    assert conn._conn is not None


def test_no_url_does_not_reconnect_and_reraises() -> None:
    """没有保存重建 URL 的连接遇到连接失效时直接抛原异常（不吞错）。"""
    conn = MySQLConnection(_FakeDeadConnection(pymysql.err.InterfaceError))  # url=None
    with pytest.raises(pymysql.err.InterfaceError):
        conn.execute("SELECT 1")


def test_non_connection_error_is_not_retried() -> None:
    """非连接失效异常（如语法错误）不被当作断线重试，原样抛出。"""
    class _SyntaxErrorConn:
        def cursor(self):
            raise pymysql.err.ProgrammingError(1064, "syntax error")

    conn = MySQLConnection(_SyntaxErrorConn(), url="mysql://u:p@h/db")
    with pytest.raises(pymysql.err.ProgrammingError):
        conn.execute("SELECT FROM WHERE")


class _ConcurrentUnsafeConn:
    """模拟 pymysql 的非线程安全：并发进入 cursor() 时抛协议错乱错误。"""

    def __init__(self):
        import threading
        self._in_use = threading.Lock()
        self.active = 0
        self.max_active = 0

    def cursor(self):
        if not self._in_use.acquire(blocking=False):
            raise pymysql.err.InternalError(0, "Packet sequence number wrong - got 1 expected 2")
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        return self

    def execute(self, sql, params):
        return (27,)

    def fetchall(self):
        self.active -= 1
        self._in_use.release()
        return ((27,),)

    def description(self):
        return None


def test_connection_is_thread_safe_under_concurrency() -> None:
    """并发 execute 必须串行化：无并发进入底层连接，全部查询成功。"""
    from concurrent.futures import ThreadPoolExecutor

    raw = _ConcurrentUnsafeConn()
    conn = MySQLConnection(raw, url="mysql://u:p@h/db")

    def query(_: int) -> tuple[bool, int]:
        try:
            result = conn.execute("SELECT COUNT(*) FROM auth_users")
            return (result.fetchone() is not None, raw.max_active)
        except BaseException:
            return (False, raw.max_active)

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(query, range(64)))

    assert all(ok for ok, _ in outcomes), "存在并发协议破坏导致的失败"
    assert raw.max_active == 1, f"底层连接被并发访问（max_active={raw.max_active}）"