"""本地数据库身份与会话边界。

本地 / Docker 使用数据库账号密码登录；密码只保存 PBKDF2 哈希，浏览器只持有
HttpOnly 会话 Cookie。生产环境仍要求网关或 Bearer 验证器接管身份。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from uuid import uuid4

from fastapi import Cookie, Depends, Header, HTTPException, status

from attribution_analysis.config.settings import settings
from attribution_analysis.infrastructure.composition import open_auth_database


SESSION_COOKIE = "attribution_session"
SESSION_TTL = timedelta(hours=8)


@dataclass(frozen=True)
class SubjectContext:
    subject_id: str
    username: str | None = None
    display_name: str | None = None
    roles: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    tenant_id: str | None = None

    def can(self, permission: str) -> bool:
        """判断当前主体是否拥有指定权限（* 表示全部权限）。"""
        return permission in self.permissions or "*" in self.permissions


class InvalidCredentialsError(Exception):
    pass


class AuthRepository:
    def __init__(self, connection) -> None:
        """初始化认证库表结构并预置本地演示账号。"""
        self.connection = connection
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS auth_users ("
            "user_id VARCHAR(255) PRIMARY KEY, username VARCHAR(255) UNIQUE NOT NULL, "
            "display_name VARCHAR(255) NOT NULL, password_hash VARCHAR(255) NOT NULL, "
            "roles VARCHAR(255) NOT NULL, tenant_id VARCHAR(255), "
            "is_active TINYINT NOT NULL DEFAULT 1, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, last_login_at TIMESTAMP)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS auth_sessions ("
            "session_id VARCHAR(255) PRIMARY KEY, token_digest VARCHAR(255) UNIQUE NOT NULL, "
            "user_id VARCHAR(255) NOT NULL, expires_at TIMESTAMP NOT NULL, "
            "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, revoked_at TIMESTAMP)"
        )
        self._seed_local_users()

    def _seed_local_users(self) -> None:
        """仅在本地/测试/Docker 环境预置演示账号（analyst/reviewer/admin）。"""
        if settings.environment not in {"local", "test", "docker"}:
            return
        count = self.connection.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0]
        if count:
            return
        users = (
            ("usr-analyst", "analyst", "经营分析员", hash_password("analyst123"), "analyst", "local"),
            ("usr-reviewer", "reviewer", "人工复核员", hash_password("reviewer123"), "reviewer", "local"),
            ("usr-admin", "admin", "系统管理员", hash_password("admin123"), "admin", "local"),
        )
        self.connection.executemany(
            "INSERT INTO auth_users (user_id, username, display_name, password_hash, roles, tenant_id) VALUES (?, ?, ?, ?, ?, ?)",
            users,
        )
        if hasattr(self.connection, 'commit'):
            self.connection.commit()

    def authenticate(self, username: str, password: str) -> SubjectContext:
        """校验用户名密码并更新最后登录时间；失败抛 InvalidCredentialsError。"""
        row = self.connection.execute(
            "SELECT user_id, username, display_name, password_hash, roles, tenant_id, is_active FROM auth_users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        if not row or not row[6] or not verify_password(password, row[3]):
            raise InvalidCredentialsError
        self.connection.execute("UPDATE auth_users SET last_login_at = CURRENT_TIMESTAMP WHERE user_id = ?", (row[0],))
        if hasattr(self.connection, 'commit'):
            self.connection.commit()
        return self._context_from_row(row)

    def register(self, username: str, display_name: str, password: str) -> SubjectContext:
        """注册新分析员账号（密码至少 8 位），返回默认 analyst 主体。"""
        username = username.strip()
        display_name = display_name.strip()
        if not username or not display_name or len(password) < 8:
            raise InvalidCredentialsError
        exists = self.connection.execute(
            "SELECT 1 FROM auth_users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            raise ValueError("账号已存在")
        subject_id = f"usr-{uuid4().hex[:12]}"
        self.connection.execute(
            "INSERT INTO auth_users (user_id, username, display_name, password_hash, roles, tenant_id) VALUES (?, ?, ?, ?, ?, ?)",
            (subject_id, username, display_name, hash_password(password), "analyst", "local"),
        )
        if hasattr(self.connection, 'commit'):
            self.connection.commit()
        return SubjectContext(subject_id, username, display_name, ("analyst",), ROLE_PERMISSIONS["analyst"], "local")

    def reset_password(self, username: str, new_password: str) -> None:
        """重置用户密码；账号不存在或密码过短时抛异常（方言中立实现）。"""
        if len(new_password) < 8:
            raise InvalidCredentialsError
        stripped = username.strip()
        row = self.connection.execute(
            "SELECT user_id FROM auth_users WHERE username = ? AND is_active = 1",
            (stripped,),
        ).fetchone()
        if not row:
            raise InvalidCredentialsError
        self.connection.execute(
            "UPDATE auth_users SET password_hash = ? WHERE user_id = ?",
            (hash_password(new_password), row[0]),
        )
        if hasattr(self.connection, 'commit'):
            self.connection.commit()

    def create_session(self, subject_id: str) -> str:
        """创建 8 小时会话并返回明文 Token（库中只存摘要）。"""
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + SESSION_TTL).replace(tzinfo=None)
        self.connection.execute(
            "INSERT INTO auth_sessions (session_id, token_digest, user_id, expires_at) VALUES (?, ?, ?, ?)",
            (uuid4().hex, digest_token(token), subject_id, expires_at),
        )
        if hasattr(self.connection, 'commit'):
            self.connection.commit()
        return token

    def subject_from_session(self, token: str | None) -> SubjectContext | None:
        """按 Token 摘要解析有效会话对应主体；无效/过期返回 None。"""
        if not token:
            return None
        row = self.connection.execute(
            """
            SELECT u.user_id, u.username, u.display_name, u.password_hash, u.roles, u.tenant_id, u.is_active,
                   s.expires_at
            FROM auth_sessions s JOIN auth_users u ON u.user_id = s.user_id
            WHERE s.token_digest = ? AND s.revoked_at IS NULL
            """,
            (digest_token(token),),
        ).fetchone()
        if not row or not row[6]:
            return None
        # 在 Python 侧做过期比较，避免 DuckDB 的 TIMESTAMP 与 CURRENT_TIMESTAMP
        # 时区/类型差异导致会话恒判过期。
        expires_at = row[7]
        try:
            if isinstance(expires_at, datetime):
                expired = expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
            else:
                expires_naive = datetime.fromisoformat(str(expires_at))
                expired = expires_naive < datetime.now(timezone.utc).replace(tzinfo=None)
        except (ValueError, TypeError):
            expired = True
        if expired:
            return None
        return self._context_from_row(row)

    def revoke_session(self, token: str | None) -> None:
        """吊销指定会话（登出）。"""
        if token:
            self.connection.execute("UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP WHERE token_digest = ?", (digest_token(token),))
            if hasattr(self.connection, 'commit'):
                self.connection.commit()

    def _context_from_row(self, row: tuple) -> SubjectContext:
        """把用户行转换为带角色权限解析的 SubjectContext。"""
        roles = tuple(item for item in row[4].split(",") if item)
        permissions = tuple(sorted({permission for role in roles for permission in ROLE_PERMISSIONS.get(role, ())}))
        return SubjectContext(row[0], row[1], row[2], roles, permissions, row[5])


ROLE_PERMISSIONS = {
    "analyst": ("cases:read", "cases:write"),
    "reviewer": ("cases:read", "reviews:write"),
    "admin": ("*",),
}


def hash_password(password: str) -> str:
    """使用 PBKDF2 加盐哈希密码。"""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"pbkdf2_sha256$210000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """用常量时间比较校验密码与 PBKDF2 哈希。"""
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(actual.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def digest_token(token: str) -> str:
    """对会话 Token 做 SHA-256 摘要（不存储明文）。"""
    return hashlib.sha256(token.encode()).hexdigest()


_repository: AuthRepository | None = None


def auth_repository() -> AuthRepository:
    """获取全局认证仓库（延迟初始化）。"""
    global _repository
    if _repository is None:
        _repository = AuthRepository(open_auth_database())
    return _repository


def current_subject(
    authorization: str | None = Header(default=None),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    x_subject_id: str | None = Header(default=None, alias="X-Subject-Id"),
) -> SubjectContext:
    """Resolve a database session locally or defer to the configured deployment verifier."""
    if settings.environment in {"local", "test", "docker"}:
        # 会话 Cookie 是唯一的本地身份来源；X-Subject-Id 旁路仅限自动化测试环境，
        # 避免 local/docker 对外暴露时任意请求头伪造身份（P0-1 修复）。
        subject = auth_repository().subject_from_session(session_token)
        if subject:
            return subject
        if x_subject_id and settings.environment == "test":
            return SubjectContext(subject_id=x_subject_id, roles=("analyst",), permissions=("cases:write", "cases:read", "evidence:read", "results:read", "plans:read"), tenant_id="local")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录会话已失效，请重新登录")

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is required")
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Token verifier is not configured")


def require_permission(permission: str):
    """返回权限检查依赖：无权限时抛 403。"""
    def dependency(subject: SubjectContext = Depends(current_subject)) -> SubjectContext:
        """FastAPI 依赖：校验当前主体权限，无权限抛 403。"""
        if not subject.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有执行该操作的权限")
        return subject

    return dependency

