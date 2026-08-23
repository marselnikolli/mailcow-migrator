from fastapi import HTTPException, Request
from app.auth import AuthService


async def get_current_user(request: Request):
    """Dependency that requires a valid JWT and attaches the caller's identity
    (user_id, tenant_id, role) to request.state. This is the sole source of
    tenant scoping for protected routes -- client-supplied headers are never
    trusted for authorization."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization header")

    token = auth_header.split(" ", 1)[1]
    payload = AuthService.decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    request.state.user_id = int(payload.get("sub"))
    request.state.tenant_id = payload.get("tenant_id")
    request.state.role = payload.get("role")

    return request.state


def require_role(allowed_roles: list):
    """Dependency factory: require a valid JWT AND one of the given roles."""

    async def check_role(request: Request):
        state = await get_current_user(request)
        if state.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return state

    return check_role
