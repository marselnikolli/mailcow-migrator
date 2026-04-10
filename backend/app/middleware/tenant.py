from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract tenant_id from X-Tenant-ID header
        tenant_id = request.headers.get("X-Tenant-ID")
        
        if not tenant_id and request.url.path not in ["/health", "/api/v1/auth/login", "/api/v1/auth/register"]:
            # Tenant ID is required for most endpoints
            if request.method != "OPTIONS":
                return JSONResponse(
                    status_code=400,
                    content={"detail": "X-Tenant-ID header is required"}
                )
        
        # Attach tenant_id to request state
        if tenant_id:
            request.state.tenant_id = int(tenant_id) if tenant_id.isdigit() else tenant_id
        else:
            request.state.tenant_id = None
        
        response = await call_next(request)
        return response
