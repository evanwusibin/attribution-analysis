"""HTTP 认证路由：登录、退出、当前身份。

所有路由挂载在 /api/v1/auth 前缀下，由 app.py 的 include_router 挂入。
"""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from attribution_analysis.api.authentication import (
    SESSION_COOKIE,
    InvalidCredentialsError,
    SubjectContext,
    auth_repository,
    current_subject,
    require_permission,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=200)


class ResetPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    new_password: str = Field(min_length=8, max_length=200)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> dict[str, object]:
    """本地注册分析员账号；生产环境应由统一身份系统接管。"""
    try:
        subject = auth_repository().register(payload.username, payload.display_name, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="注册信息不合法") from exc
    return {"request_id": "local-request", "data": {"username": subject.username, "display_name": subject.display_name}}


@router.post("/forgot-password")
def forgot_password(payload: ResetPasswordRequest) -> dict[str, object]:
    """本地演示环境的密码重置；正式环境应替换为邮件/短信验证码流程。"""
    try:
        auth_repository().reset_password(payload.username, payload.new_password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在或密码不符合要求") from exc
    return {"request_id": "local-request", "data": {"status": "password_reset"}}


@router.post("/login")
def login(payload: LoginRequest, response: Response) -> dict[str, object]:
    """账号密码登录，设置 HttpOnly 会话 Cookie。"""
    repo = auth_repository()
    try:
        subject = repo.authenticate(payload.username, payload.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        )

    token = repo.create_session(subject.subject_id)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # 本地 HTTP；生产环境改为 True
        max_age=28800,  # 8 小时
        path="/",
    )
    return {
        "request_id": "local-request",
        "data": {
            "subject_id": subject.subject_id,
            "username": subject.username,
            "display_name": subject.display_name,
            "roles": list(subject.roles),
            "permissions": list(subject.permissions),
        },
    }


@router.post("/logout")
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """退出登录，撤销服务端会话并清除浏览器 Cookie。"""
    auth_repository().revoke_session(session_token)
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=False,
    )
    return {"request_id": "local-request", "data": {"status": "logged_out"}}


@router.get("/me")
def me(
    subject: SubjectContext = Depends(current_subject),
) -> dict[str, object]:
    """返回当前会话的身份、角色与权限。"""
    return {
        "request_id": "local-request",
        "data": {
            "subject_id": subject.subject_id,
            "username": subject.username,
            "display_name": subject.display_name,
            "roles": list(subject.roles),
            "permissions": list(subject.permissions),
            "tenant_id": subject.tenant_id,
        },
    }