from fastapi import Header, HTTPException, Request
from .config import settings
from .crypto import verify_user_token

async def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    """Require API key for sensitive endpoints"""
    if not settings.PYTHON_API_KEY:
        return  # Skip API key check if not configured
    if not x_api_key or x_api_key != settings.PYTHON_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

async def require_admin_or_api_key(request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    """
    Require either JWT authentication with admin role OR API key authentication.
    This allows logged-in admin users to access admin endpoints without needing an API key.
    """
    # Check JWT authentication first (for admin users)
    claims = try_get_current_user_claims(request)
    is_admin = False
    
    if claims:
        # JWT token uses "role" field (set by issue_user_token)
        user_role = claims.get("role")
        # Also check user_type as fallback (some tokens might use this)
        if not user_role:
            user_role = claims.get("user_type")
        
        if user_role == "admin":
            is_admin = True
            print(f"[AUTH] Admin user authenticated via JWT: {claims.get('sub')} (role: {user_role})")
        else:
            print(f"[AUTH] Non-admin user attempted admin endpoint: {user_role} (claims: {list(claims.keys())})")
            raise HTTPException(status_code=403, detail="Only admin users can access this endpoint")
    
    # If not admin via JWT, require API key
    if not is_admin:
        if not settings.PYTHON_API_KEY:
            # Skip API key check if not configured (development mode)
            print(f"[AUTH] API key not configured, allowing access (development mode)")
            return
        if not x_api_key or x_api_key != settings.PYTHON_API_KEY:
            print(f"[AUTH] Invalid or missing API key")
            raise HTTPException(status_code=401, detail="Authentication required: API key or admin JWT token")
        print(f"[AUTH] API key authenticated")

def get_current_user_claims(request: Request):
    """Extract JWT from Authorization Bearer header or cookie 'auth_token'."""
    token = None
    
    # Try Authorization header first
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        token = auth.split(None, 1)[1].strip()
    
    # Fallback to cookie
    if not token:
        token = request.cookies.get("auth_token")
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    claims = verify_user_token(token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token")
    
    return claims

def try_get_current_user_claims(request: Request):
    """
    Extract JWT claims if available, but do not raise an error if not authenticated.
    Returns claims dict or None.
    """
    try:
        return get_current_user_claims(request)
    except HTTPException as e:
        # If auth fails (e.g., no token, invalid token), return None instead of raising
        if e.status_code in [401, 403]:
            return None
        raise

def get_current_user_id(request: Request) -> str:
    """Get current user ID from JWT token"""
    claims = get_current_user_claims(request)
    return claims.get("sub")

def require_user_type(request: Request, allowed_types: list[str]):
    """Require specific user types"""
    claims = get_current_user_claims(request)
    user_type = claims.get("role")
    
    if user_type not in allowed_types:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    return claims

def require_admin(request: Request):
    """Require admin user type"""
    return require_user_type(request, ["admin"])