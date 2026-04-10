from fastapi import HTTPException, Depends, Request, status
from app.auth import AuthService

async def require_role(allowed_roles: list):
    """Dependency to check if user has required role."""
    async def check_role(request: Request):
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing authorization header")
        
        token = auth_header.split(" ")[1]
        payload = AuthService.decode_token(token)
        
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user_role = payload.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        
        # Attach user info to request
        request.state.user_id = payload.get("sub")
        request.state.tenant_id = payload.get("tenant_id")
        request.state.role = user_role
        
        return request.state
    
    return check_role
