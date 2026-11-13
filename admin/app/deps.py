from fastapi import HTTPException, Request


def current_user(request: Request) -> dict | None:
    return request.session.get("user")


def require_user(request: Request) -> dict:
    """API 用：未登录返回 401（页面用 redirect，见 pages 路由）。"""
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user
