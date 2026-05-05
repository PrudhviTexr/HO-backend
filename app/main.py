import os
import re
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
import datetime as dt
import traceback as tb

from .core.config import settings

app = FastAPI(
    title="Home & Own Python API",
    description="API for Home & Own, a real estate platform.",
    version="1.0.0"
)

# Middleware
cors_origins = []

# IMPORTANT: When allow_credentials=True, we CANNOT use wildcard "*"
# We must explicitly list all allowed origins

# PRODUCTION SETUP: All allowed origins come from CORS_ORIGIN environment variable
# This keeps the code free of hardcoded values and safe for deployment
print("[CORS] Initializing CORS configuration from environment...")

# Get allowed origins from environment variable
# Example in .env: CORS_ORIGIN=https://homeandown.com,https://www.homeandown.com
cors_raw = getattr(settings, 'CORS_ORIGIN', '') or ''
if cors_raw:
    cors_origins = [o.strip() for o in cors_raw.split(',') if o.strip()]
    print(f"[CORS] ✅ Loaded {len(cors_origins)} origin(s) from CORS_ORIGIN environment variable")
else:
    print("[CORS] ⚠️  WARNING: CORS_ORIGIN environment variable is empty or not set!")
    print("[CORS] The API will reject requests from any origin.")
    print("[CORS] Set CORS_ORIGIN in .env to enable CORS (comma-separated URLs)")

# Mobile/WebView origins (Capacitor, Ionic, null) so the mobile app can open and call the API
mobile_raw = getattr(settings, 'CORS_ORIGIN_MOBILE', '') or ''
if mobile_raw:
    for o in mobile_raw.split(','):
        o = o.strip()
        if o and o not in cors_origins:
            cors_origins.append(o)
    print(f"[CORS] ✅ Mobile/WebView origins included (CORS_ORIGIN_MOBILE)")

# Safety check: Ensure production domains are always accessible
PRODUCTION_ORIGINS = ["https://homeandown.com", "https://www.homeandown.com"]
for origin in PRODUCTION_ORIGINS:
    if origin not in cors_origins:
        cors_origins.append(origin)
        print(f"[CORS] ✅ Added production origin: {origin}")

# Summary
print(f"[CORS] Final configuration: {len(cors_origins)} origin(s) allowed")
if cors_origins:
    for origin in cors_origins:
        print(f"  - {origin}")
else:
    print("  ⚠️  No origins configured!")

# Regex for mobile/WebView origins (Capacitor, Ionic)
# Ensures the new mobile app can open and call the API even with variant origins
_CORS_ORIGIN_REGEX = (
    r"^capacitor://.*"
    r"|^ionic://.*"
)

# Store so exception handler and any other code use the same list
app._cors_origins = list(cors_origins)
app._cors_origin_regex = _CORS_ORIGIN_REGEX

# Add CORS middleware - MUST be first middleware to ensure it handles all responses
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,  # Explicit list (required when allow_credentials=True)
    allow_origin_regex=_CORS_ORIGIN_REGEX,  # Mobile/WebView: capacitor://*, ionic://*
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Production origins always get CORS headers (safety net)
_ALWAYS_ALLOW_ORIGINS = ("https://homeandown.com", "https://www.homeandown.com")

def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    if origin in cors_origins or origin in _ALWAYS_ALLOW_ORIGINS:
        return True
    try:
        return bool(re.match(_CORS_ORIGIN_REGEX, origin))
    except Exception:
        return False

# Custom middleware to ensure CORS headers are always added
class EnsureCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        response = await call_next(request)
        allowed = _origin_allowed(origin)
        if origin:
            print(f"[CORS] Request from origin: {origin}, Allowed: {allowed}")
        if allowed:
            if "Access-Control-Allow-Origin" not in response.headers:
                response.headers["Access-Control-Allow-Origin"] = origin
            if "Access-Control-Allow-Credentials" not in response.headers:
                response.headers["Access-Control-Allow-Credentials"] = "true"
        elif origin:
            print(f"[CORS] WARNING: Origin {origin} not in allowed list. Allowed origins: {cors_origins}")
        return response

# Add custom CORS middleware after CORS middleware
app.add_middleware(EnsureCORSMiddleware)

# Production origins always allowed for OPTIONS (safety net if list is wrong on deploy)
_OPTIONS_ALWAYS_ORIGINS = ("https://homeandown.com", "https://www.homeandown.com")

# Add explicit OPTIONS handler for preflight requests
@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    """Handle OPTIONS preflight requests"""
    origin = request.headers.get("origin")
    print(f"[CORS] OPTIONS preflight request from origin: {origin}")
    allowed = _origin_allowed(origin)
    if allowed:
        response = Response(status_code=204)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Max-Age"] = "3600"
        print(f"[CORS] Allowed OPTIONS request from {origin}")
        return response
    if origin:
        print(f"[CORS] Rejected OPTIONS request from {origin} (not in allowed list)")
    return Response(status_code=400)

# Import routes after app initialization to avoid circular dependencies
from .routes import (
    auth, properties, users, uploads, records, maintenance,
    seller, buyer, emails, agent, locations, analytics, admin,
    push_notifications, advanced_analytics, role_based
)
from .routes import auth_otp, agent_assignments

@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    print("============================================================")
    print("Home & Own Python API Starting Up...")
    print("============================================================")
    print(f"Site URL: {settings.SITE_URL}")
    print(f"CORS Origins from settings: {[origin.strip() for origin in settings.CORS_ORIGIN.split(',')]}")
    print(f"CORS Origins actually configured: {cors_origins}")
    print(f"Email configured: {bool(settings.GMAIL_USERNAME and settings.GMAIL_APP_PASSWORD)}")
    print(f"SMS/OTP configured: {bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN)}")
    print(f"Supabase URL: {bool(settings.SUPABASE_URL)}")
    print(f"API Key configured: {bool(settings.PYTHON_API_KEY)}")

    # Test and report database connection on startup
    try:
        from .db.supabase_client import db
        print(f"[DB] Testing Supabase database connection...")
        sample_data = await db.select("properties", limit=1)
        print(f"[DB] Supabase connection successful! Sample data: {len(sample_data)} properties")

        # Fetch and print database statistics
        users_count_res = await db.select("users", select="count")
        properties_count_res = await db.select("properties", select="count")
        bookings_count_res = await db.select("bookings", select="count")
        
        users_count = users_count_res[0]['count'] if users_count_res else 0
        properties_count = properties_count_res[0]['count'] if properties_count_res else 0
        bookings_count = bookings_count_res[0]['count'] if bookings_count_res else 0
        
        print("\n" + "="*60)
        print("📊 DATABASE STATISTICS")
        print("="*60)
        print(f"👥 Total users: {users_count}")
        print(f"🏠 Total properties: {properties_count}")
        print(f"📅 Total bookings: {bookings_count}")
        print("="*60 + "\n")

    except Exception as e:
        print(f"[DB] Supabase connection or query failed: {e}")

    # Ensure default admin user exists (only if credentials are provided)
    try:
        from .core.crypto import get_password_hash
        from .db.supabase_client import db
        # Admin credentials must be set via environment variables
        ADMIN_EMAIL = os.getenv('DEFAULT_ADMIN_EMAIL', '')
        ADMIN_PASSWORD = os.getenv('DEFAULT_ADMIN_PASSWORD', '')
        
        # Only create admin if both email and password are provided
        if ADMIN_EMAIL and ADMIN_PASSWORD:
            users = await db.select('users', filters={'email': ADMIN_EMAIL})
            if not users:
                print("[DB] Default admin not found, creating...")
                await db.insert('users', {
                    'email': ADMIN_EMAIL,
                    'password_hash': get_password_hash(ADMIN_PASSWORD),
                    'user_type': 'admin',
                    'first_name': 'Admin',
                    'last_name': 'User',
                    'status': 'active',
                    'verification_status': 'verified',
                    'email_verified': True
                })
                print(f"[DB] Default admin created: {ADMIN_EMAIL}")
            else:
                print(f"[DB] Default admin already exists: {ADMIN_EMAIL}")
        else:
            print("[DB] DEFAULT_ADMIN_EMAIL and DEFAULT_ADMIN_PASSWORD not set - skipping admin user creation")
    except Exception as e:
        print(f"[DB] Could not ensure default admin: {e}")

    print("============================================================")
    print("API Ready and Listening!")
    print("============================================================")

# Include routers with prefixes
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(auth_otp.router, prefix="/api/auth", tags=["auth"])
app.include_router(properties.router, prefix="/api/properties", tags=["properties"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(uploads.router, prefix="/api/uploads", tags=["uploads"])
app.include_router(records.router, prefix="/api/records", tags=["records"])
app.include_router(maintenance.router, prefix="/api/maintenance", tags=["maintenance"])
app.include_router(seller.router, prefix="/api/seller", tags=["seller"])
app.include_router(buyer.router, prefix="/api/buyer", tags=["buyer"])
app.include_router(emails.router, prefix="/api/emails", tags=["emails"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(agent_assignments.router, prefix="/api", tags=["agent-assignments"])
app.include_router(locations.router, prefix="/api/locations", tags=["locations"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(advanced_analytics.router, prefix="/api", tags=["advanced-analytics"])
app.include_router(push_notifications.router, prefix="/api", tags=["push-notifications"])
app.include_router(role_based.router, prefix="/api/role-based", tags=["role-based"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler to ensure errors are properly handled"""
    print(f"[ERROR] Unhandled exception: {exc}")
    print(f"[ERROR] Traceback: {tb.format_exc()}")
    
    # Create response with CORS headers
    response = JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"}
    )
    
    # Ensure CORS headers are present even on errors (including mobile/WebView origins)
    origin = request.headers.get("origin")
    if origin and _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "*"
    
    return response

@app.get("/", tags=["Root"])
async def read_root():
    """Root endpoint - redirects to /api"""
    return {"message": f"Welcome to Home & Own API - {dt.datetime.utcnow()}", "api_endpoint": "/api"}

@app.get("/api", tags=["Root"])
async def read_api_root():
    """API root endpoint"""
    return {"message": f"Welcome to Home & Own API - {dt.datetime.utcnow()}"}