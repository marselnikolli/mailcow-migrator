from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from app.auth import AuthService
from app.db import get_db, dict_from_row
from app.models import UserRole

router = APIRouter()

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_name: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_id: int

class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    tenant_id: int

@router.post("/register")
async def register(request: RegisterRequest):
    """Register a new user and tenant."""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Create tenant
        cursor.execute("INSERT INTO tenants (name) VALUES (?)", (request.tenant_name,))
        tenant_id = cursor.lastrowid
        
        # Hash password
        password_hash = AuthService.hash_password(request.password)
        
        # Create user as owner
        cursor.execute("""
            INSERT INTO users (tenant_id, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        """, (tenant_id, request.email, password_hash, UserRole.OWNER.value))
        
        user_id = cursor.lastrowid
        conn.commit()
        
        # Generate token
        token_response = AuthService.create_token_response(user_id, tenant_id, UserRole.OWNER.value)
        return token_response
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()

@router.post("/login")
async def login(request: LoginRequest):
    """Login user and return token."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user
    cursor.execute("""
        SELECT * FROM users 
        WHERE email = ? AND tenant_id = ?
    """, (request.email, request.tenant_id))
    
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user = dict_from_row(user_row)
    
    # Verify password
    if not AuthService.verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate token
    token_response = AuthService.create_token_response(user["id"], user["tenant_id"], user["role"])
    return token_response

@router.get("/me", response_model=UserResponse)
async def get_current_user(token: str):
    """Get current user info from token."""
    payload = AuthService.decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ? AND tenant_id = ?", (user_id, tenant_id))
    user_row = cursor.fetchone()
    conn.close()
    
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")
    
    user = dict_from_row(user_row)
    return UserResponse(
        id=user["id"],
        email=user["email"],
        role=user["role"],
        tenant_id=user["tenant_id"]
    )
