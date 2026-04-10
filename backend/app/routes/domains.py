from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from app.core.domains import DomainService
from app.db import get_db, dict_from_row
from typing import List

router = APIRouter()
domain_service = DomainService()

class DomainCreateRequest(BaseModel):
    domain: str

@router.post("/add")
async def add_domain(request: Request, domain_data: DomainCreateRequest):
    """Add a domain."""
    tenant_id = request.state.tenant_id
    domain = domain_data.domain
    
    try:
        domain_service.ensure_domain_exists(domain, tenant_id)
        return {
            "status": "success",
            "domain": domain,
            "message": "Domain added successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/list")
async def list_domains(request: Request):
    """List domains for tenant."""
    tenant_id = request.state.tenant_id
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, domain, created_in_mailcow, created_at 
        FROM domains 
        WHERE tenant_id = ?
        ORDER BY created_at DESC
    """, (tenant_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    domains = []
    for row in rows:
        row_dict = dict_from_row(row)
        domains.append({
            "id": row_dict["id"],
            "domain": row_dict["domain"],
            "created_in_mailcow": bool(row_dict["created_in_mailcow"]),
            "created_at": row_dict["created_at"]
        })
    
    return domains

@router.get("/validate/{domain}")
async def validate_domain(request: Request, domain: str):
    """Validate domain exists in Mailcow."""
    try:
        exists = domain_service.mailcow.check_domain_exists(domain)
        return {
            "domain": domain,
            "exists": exists,
            "in_mailcow": exists
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
