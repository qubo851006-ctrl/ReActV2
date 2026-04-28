import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from auth_utils import SESSION_DAYS, _hash, create_session, get_current_user
from db import get_db
from models import User, UserSession

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/users-lite")
def users_lite(db: DBSession = Depends(get_db)):
    """公开接口：返回启用用户列表，供登录页选择姓名。"""
    users = db.query(User).filter_by(status="active").order_by(User.name).all()
    return {
        "users": [
            {"id": u.id, "name": u.name, "department": u.department}
            for u in users
        ]
    }


class BindRequest(BaseModel):
    user_id: int
    short_code: str


@router.post("/bind-device")
def bind_device(
    req: BindRequest,
    request: Request,
    response: Response,
    db: DBSession = Depends(get_db),
):
    """首次短码验证，成功后写入 HttpOnly Cookie。"""
    user = db.get(User, req.user_id)
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="姓名或短码不正确")
    code_hash = hashlib.sha256(req.short_code.strip().encode()).hexdigest()
    if not user.short_code_hash or user.short_code_hash != code_hash:
        raise HTTPException(status_code=401, detail="姓名或短码不正确")

    token = create_session(db, user, request)
    response.set_cookie(
        key="sid",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "department": user.department,
            "role": user.role,
        }
    }


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    """返回当前登录用户信息。"""
    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "department": user.department,
            "role": user.role,
            "last_login_at": user.last_login_at,
        }
    }


@router.post("/logout")
def logout(
    response: Response,
    db: DBSession = Depends(get_db),
    sid: str | None = Cookie(default=None),
):
    """吊销当前会话，清除 Cookie。"""
    if sid:
        sess = db.query(UserSession).filter_by(token_hash=_hash(sid)).first()
        if sess:
            sess.revoked_at = datetime.now(timezone.utc)
            db.commit()
    response.delete_cookie("sid", path="/")
    return {"ok": True}
