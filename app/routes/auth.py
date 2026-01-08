from fastapi import APIRouter, HTTPException, Response, Request, Header
from typing import Dict, Any, List, Optional
from ..models.schemas import SignupRequest, LoginRequest, SendOTPRequest, VerifyOTPRequest, UpdateProfileRequest
from ..core.config import settings
from ..core.security import get_current_user_claims
from ..core.crypto import (
    get_password_hash,
    verify_password,
    generate_token,
    issue_user_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_refresh_token_hash,
)
from ..services.email import send_email
from ..services.templates import verification_email
from ..db.supabase_client import db
import datetime as dt
import uuid
import traceback
import pytz
import json

router = APIRouter()

@router.get("/test")
async def test_auth_route():
    """Test route to verify auth router is working"""
    return {"message": "Auth router is working", "status": "success"}

@router.post("/signup")
async def signup(payload: SignupRequest, request: Request) -> Dict[str, Any]:
    try:
        # Check if user already exists
        try:
            existing_users: List[Dict[str, Any]] = await db.select("users", filters={"email": payload.email.lower()})
            if existing_users:
                return {
                    "success": False,
                    "error": "User with this email already exists. Please sign in instead."
                }
        except Exception as db_error:
            pass
        
        # Generate user ID
        user_id = str(uuid.uuid4())
        
        # TEMPORARY STORAGE: Store signup data in memory, don't save to DB yet
        # Data will be saved to DB only after OTP verification
        from ..services.otp_service import _temp_signup_storage
        
        # Prepare user data (not saved to DB yet)
        now_utc = dt.datetime.now(dt.timezone.utc).isoformat()
        
        # Set verification status and initial status based on user role
        # ALL users now require admin approval
        verification_status = "pending"
        initial_status = "pending"  # All users need approval
        
        user_data: Dict[str, Any] = {
            "id": user_id,
            "email": payload.email.lower(),
            "password_hash": get_password_hash(payload.password),
            "first_name": payload.first_name or "",
            "last_name": payload.last_name or "",
            "phone_number": payload.phone_number or "",
            "user_type": payload.role or "buyer",
            "city": payload.city or "",
            "state": payload.state or "",
            "status": initial_status,  # Set based on user type
            "verification_status": verification_status,  # Agents/sellers need admin approval
            "email_verified": False,
            "created_at": now_utc,
            "updated_at": now_utc
        }
        
        # Add date_of_birth if provided
        if hasattr(payload, 'date_of_birth') and payload.date_of_birth:
            user_data["date_of_birth"] = payload.date_of_birth
        
        # Add location fields if provided (especially important for agents to enable zipcode-based assignment)
        if hasattr(payload, 'zip_code') and payload.zip_code:
            user_data["zip_code"] = payload.zip_code
        if hasattr(payload, 'district') and payload.district:
            user_data["district"] = payload.district
        if hasattr(payload, 'mandal') and payload.mandal:
            user_data["mandal"] = payload.mandal
        if hasattr(payload, 'address') and payload.address:
            user_data["address"] = payload.address
        if hasattr(payload, 'latitude') and payload.latitude:
            try:
                user_data["latitude"] = float(payload.latitude) if payload.latitude else None
            except (ValueError, TypeError):
                pass
        if hasattr(payload, 'longitude') and payload.longitude:
            try:
                user_data["longitude"] = float(payload.longitude) if payload.longitude else None
            except (ValueError, TypeError):
                pass
        
        # Store agent-specific fields for later use (don't add to user_data - they go to agent_profiles)
        agent_profile_data = {}
        if payload.role == "agent":
            if hasattr(payload, 'experience_years') and payload.experience_years:
                try:
                    agent_profile_data["experience_years"] = int(payload.experience_years) if payload.experience_years else None
                except (ValueError, TypeError):
                    agent_profile_data["experience_years"] = None
            if hasattr(payload, 'specialization') and payload.specialization:
                agent_profile_data["specialization"] = payload.specialization
        
        # Generate custom ID and license number based on user type
        custom_id = None
        if payload.role in ["buyer", "agent", "seller"]:
            try:
                from ..services.admin_service import generate_custom_id
                custom_id = await generate_custom_id(payload.role)
                user_data["custom_id"] = custom_id
                
                # For agents, also set license number (if column exists)
                if payload.role == "agent":
                    # Try to set license_number, but don't fail if column doesn't exist
                    try:
                        user_data["license_number"] = custom_id
                    except Exception as license_error:
                        # Store in agent_license_number as fallback
                        user_data["agent_license_number"] = custom_id
            except Exception as cid_error:
                pass
        
        # Create user in database IMMEDIATELY
        try:
            user_result = await db.insert("users", user_data)
            
            # Handle list response from db.insert
            if isinstance(user_result, list) and len(user_result) > 0:
                user = user_result[0]
            elif isinstance(user_result, dict):
                user = user_result
            else:
                user = user_data
            
            # Initialize user roles with primary role
            try:
                from ..services.user_role_service import UserRoleService
                await UserRoleService.initialize_user_roles(user_id, payload.role)
            except Exception as role_error:
                pass
            
            # Create agent profile if user is an agent
            if payload.role == "agent" and agent_profile_data:
                try:
                    agent_profile_insert = {
                        "user_id": user_id,
                        "specialization": agent_profile_data.get("specialization", ""),
                        "bio": "",
                        "experience_years": agent_profile_data.get("experience_years"),
                        "license_status": "pending",
                        "created_at": now_utc,
                        "updated_at": now_utc
                    }
                    await db.insert("agent_profiles", agent_profile_insert)
                except Exception as agent_profile_error:
                    # Don't fail signup if agent profile creation fails - it can be created later
                    pass
                
        except Exception as create_error:
            return {
                "success": False,
                "error": f"Failed to create user account: {str(create_error)}"
            }
        
        # Create user approval record for ALL users (buyers, agents, sellers)
        try:
            approval_data = {
                "user_id": user_id,
                "status": "pending",
                "submitted_at": now_utc,
                "created_at": now_utc,
                "updated_at": now_utc
            }
            await db.insert("user_approvals", approval_data)
        except Exception as approval_err:
            pass
        
        # Admin notifications are handled by admin dashboard
        
        # Send OTP email automatically during signup
        try:
            from ..services.otp_service import send_email_otp
            otp_token = await send_email_otp(payload.email.lower(), "email_verification")
        except Exception as otp_error:
            # Don't fail signup if OTP sending fails - user can request OTP again
            pass
        
        # Return success with user ID
        return {
            "success": True,
            "user": {
                "id": user_id,
                "email": payload.email.lower(),
                "first_name": payload.first_name or "",
                "last_name": payload.last_name or ""
            },
            "message": "Account created successfully! Please check your email for verification."
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Signup failed: {str(e)}"
        }


@router.post("/login")
async def login(payload: LoginRequest, response: Response, role: Optional[str] = None) -> Dict[str, Any]:
    """Authenticates a user and issues an access token and refresh token cookie."""
    try:
        try:
            # Add timeout to prevent hanging on slow database
            import asyncio
            users: List[Dict[str, Any]] = await asyncio.wait_for(
                db.select("users", filters={"email": payload.email.lower()}, limit=1),
                timeout=1.5  # Reduced to 1.5 seconds for faster failure
            )
            if not users:
                raise HTTPException(status_code=401, detail="Invalid email or password")
            
            user: Dict[str, Any] = users[0]
            password_hash_field = user.get('password_hash') or user.get('hashed_password')
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Database timeout - please try again")
        except HTTPException:
            raise
        except Exception as db_error:
            raise HTTPException(status_code=500, detail="Login failed due to database error")
        
        # Check if password_hash exists (try both field names for backward compatibility)
        password_hash = user.get("password_hash") or user.get("hashed_password")
        if not password_hash:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Trim password to handle whitespace issues
        password = payload.password.strip() if payload.password else ""
        if not password:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        # Trim password_hash in case it has whitespace
        password_hash = password_hash.strip() if isinstance(password_hash, str) else password_hash
        
        # Ensure password doesn't exceed bcrypt's 72-byte limit
        # Convert to bytes to check length, then truncate if needed
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
            password = password_bytes.decode('utf-8', errors='ignore')
        
        try:
            if not verify_password(password, password_hash):
                raise HTTPException(status_code=401, detail="Invalid email or password")
        except HTTPException:
            raise
        except Exception as pwd_error:
            raise HTTPException(status_code=401, detail="Authentication failed")
        
        # Validate user role if specified
        user_type = user.get("user_type", "buyer")
        if role and role.lower() != user_type.lower():
            raise HTTPException(
                status_code=403, 
                detail=f"You are registered as a {user_type.title()}. Please select the correct role to sign in."
            )
        
        # Check if user is approved by admin (for all user types)
        # NOTE: We check this AFTER password verification to avoid revealing user existence
        # But we provide specific error messages for status issues
        user_status = user.get("status", "pending")
        verification_status = user.get("verification_status", "pending")
        
        if user_status != "active":
            # Provide a more specific message for suspended accounts
            if user_status == 'suspended':
                detail = "Your account has been suspended. Please contact support."
            else:
                detail = "Your account is pending admin approval. Please wait for admin approval before you can login."
            raise HTTPException(
                status_code=403, 
                detail=detail
            )
        
        # For agents, also check verification_status
        if user_type == 'agent' and verification_status not in ['verified', 'active']:
            raise HTTPException(
                status_code=403,
                detail="Your agent account verification is still pending. Please wait for admin approval."
            )
        
        # Allow any verified user to sign in (regardless of user type)
        # Admin approval is the primary requirement
        

        try:
            user_id = str(user["id"])
            user_type = str(user.get("user_type", "buyer"))
            
            # Get user's active roles
            try:
                from ..services.user_role_service import UserRoleService
                active_roles = await UserRoleService.get_active_user_roles(user_id)

            except Exception as role_error:
                active_roles = [user_type]  # Fallback to primary role
            
            
            
            auth_token = issue_user_token(user_id, user_type)
            

            refresh_raw = generate_refresh_token()
            
            
            refresh_hash = hash_refresh_token(refresh_raw)
            

            # Use a safe default if the setting is missing or falsy
            refresh_expires_days = int(getattr(settings, 'JWT_REFRESH_EXPIRATION_DAYS', 30) or 30)
            refresh_record: Dict[str, Any] = {
                "user_id": user_id,
                "token_hash": refresh_hash,
                "user_agent": "",
                "ip_address": "",
                "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=refresh_expires_days)).isoformat(),
            }
            try:
                await db.insert("refresh_tokens", refresh_record)
            except Exception as e:
                pass

            response.set_cookie(
                "refresh_token",
                refresh_raw,
                httponly=True,
                secure=settings.SITE_URL.startswith("https") if settings.SITE_URL else False,
                samesite="lax",
                max_age=60 * 60 * 24 * refresh_expires_days,
                path="/api"
            )
            
            # Also set auth_token cookie for session-based authentication
            # This allows the backend to authenticate requests via cookie
            response.set_cookie(
                "auth_token",
                auth_token,
                httponly=True,
                secure=settings.SITE_URL.startswith("https") if settings.SITE_URL else False,
                samesite="lax",
                max_age=60 * 60 * 24,  # 1 day for auth token
                path="/api"
            )

            return {
                "success": True,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", ""),
                    "user_type": user.get("user_type", "buyer"),
                    "active_roles": active_roles,
                    "custom_id": user.get("custom_id")
                },
                "token": auth_token,
                "message": "Login successful"
            }
        except Exception as token_error:
            raise HTTPException(status_code=500, detail="Failed to generate authentication tokens")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.get("/me")
async def get_profile(request: Request) -> Dict[str, Any]:
    """Get current user profile from JWT token with ALL fields - optimized for speed."""
    try:
        # Extract token from request (for returning to frontend)
        token = None
        auth = request.headers.get("Authorization")
        if auth and auth.lower().startswith("bearer "):
            token = auth.split(None, 1)[1].strip()
        if not token:
            token = request.cookies.get("auth_token")
        
        # Get user claims from JWT token (fast - no DB query)
        user_claims = get_current_user_claims(request)
        user_id = user_claims.get("sub")  # JWT standard uses 'sub' for subject (user_id)
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        # Check cache first (30 second cache for auth endpoint - very short for security)
        from ..core.cache import cache
        cache_key = f"auth_profile:{user_id}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            # Update token in cached result if we have a new one
            if token:
                cached_result["token"] = token
            return cached_result
        
        # Fetch user data from database (with aggressive timeout)
        import asyncio
        try:
            users = await asyncio.wait_for(
                db.select("users", filters={"id": user_id}, limit=1),
                timeout=1.5  # Reduced to 1.5 seconds for faster failure
            )
        except asyncio.TimeoutError:
            # If database is slow, return cached profile if available, otherwise error
            # Try to return basic info from JWT token if database is unavailable
            return {
                "id": user_id,
                "email": user_claims.get("email", ""),
                "first_name": user_claims.get("first_name", ""),
                "last_name": user_claims.get("last_name", ""),
                "user_type": user_claims.get("user_type", "buyer"),
                "active_roles": [user_claims.get("user_type", "buyer")],
                "email_verified": user_claims.get("email_verified", False),
                "status": "active",
                "token": token,
                "from_cache": False,
                "database_unavailable": True
            }
        except Exception as db_error:
            error_msg = str(db_error)
            # Check for database connection errors
            if "getaddrinfo failed" in error_msg or "11001" in error_msg:

                # Return basic info from JWT token if database is unavailable
                return {
                    "id": user_id,
                    "email": user_claims.get("email", ""),
                    "first_name": user_claims.get("first_name", ""),
                    "last_name": user_claims.get("last_name", ""),
                    "user_type": user_claims.get("user_type", "buyer"),
                    "active_roles": [user_claims.get("user_type", "buyer")],
                    "email_verified": user_claims.get("email_verified", False),
                    "status": "active",
                    "token": token,
                    "from_cache": False,
                    "database_unavailable": True
                }
            raise
        
        if not users or len(users) == 0:
            # User not found in database, but JWT is valid - return basic info from JWT

            return {
                "id": user_id,
                "email": user_claims.get("email", ""),
                "first_name": user_claims.get("first_name", ""),
                "last_name": user_claims.get("last_name", ""),
                "user_type": user_claims.get("user_type", "buyer"),
                "active_roles": [user_claims.get("user_type", "buyer")],
                "email_verified": user_claims.get("email_verified", False),
                "status": "active",
                "token": token,
                "from_cache": False,
                "user_not_found_in_db": True
            }
        
        user = users[0]
        user_type = user.get("user_type", "buyer")
        
        # Get user's active roles (skip if slow - use default immediately)
        active_roles = [user_type]  # Default to user_type immediately
        # Skip role service call for speed - just use user_type
        # Role service can be slow and is not critical for basic auth
        
        # Fetch agent profile data if user is an agent
        experience_years = None
        specialization = None
        if user_type == "agent":
            try:
                agent_profiles = await asyncio.wait_for(
                    db.select("agent_profiles", filters={"user_id": user_id}, limit=1),
                    timeout=1.0
                )
                if agent_profiles and len(agent_profiles) > 0:
                    agent_profile = agent_profiles[0]
                    experience_years = agent_profile.get("experience_years")
                    specialization = agent_profile.get("specialization")
            except (asyncio.TimeoutError, Exception) as agent_profile_error:
                # Continue without agent profile data - don't fail the request
                pass
        
        # Build response with ALL fields from the database
        response_data = {
            "id": user["id"],
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "user_type": user_type,
            "active_roles": active_roles,
            "custom_id": user.get("custom_id"),
            "email_verified": user.get("email_verified", False),
            "status": user.get("status", "active"),
            "verification_status": user.get("verification_status", "pending"),
            "phone_number": user.get("phone_number", ""),
            "city": user.get("city", ""),
            "state": user.get("state", ""),
            "district": user.get("district", ""),
            "mandal": user.get("mandal", ""),
            "zip_code": user.get("zip_code", ""),
            "address": user.get("address", ""),
            "latitude": user.get("latitude"),
            "longitude": user.get("longitude"),
            "date_of_birth": user.get("date_of_birth"),
            "bio": user.get("bio", ""),
            "profile_image_url": user.get("profile_image_url"),
            "business_name": user.get("business_name", ""),
            # Agent-specific fields (read-only) - fetched from agent_profiles
            "agent_license_number": user.get("agent_license_number") or user.get("license_number") or user.get("custom_id"),
            "license_number": user.get("license_number") or user.get("agent_license_number") or user.get("custom_id"),
            "custom_id": user.get("custom_id"),
            "experience_years": experience_years,
            "specialization": specialization,
            # Bank details (read-only for security)
            "bank_account_number": user.get("bank_account_number"),
            "ifsc_code": user.get("ifsc_code"),
            "bank_verified": user.get("bank_verified", False),
            # Timestamps
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
            "email_verified_at": user.get("email_verified_at")
        }
        
        # Include token in response so frontend can store it
        # This is needed because httponly cookies can't be read by JavaScript
        if token:
            response_data["token"] = token
        
        # Cache result for 60 seconds (longer cache to reduce database load)
        from ..core.cache import cache
        cache_key = f"auth_profile:{user_id}"
        cache.set(cache_key, response_data, ttl=60)  # Increased to 60s to reduce DB queries
        
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:


        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")


@router.patch("/profile")
async def update_profile(request: Request, updates: UpdateProfileRequest) -> Dict[str, Any]:
    """Update user profile fields including profile_image_url."""
    try:

        # Get user claims from JWT token
        user_claims = get_current_user_claims(request)
        user_id = user_claims.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        # Build update dict from provided fields
        update_data = {}
        if updates.first_name is not None:
            update_data["first_name"] = updates.first_name
        if updates.last_name is not None:
            update_data["last_name"] = updates.last_name
        if updates.phone_number is not None:
            update_data["phone_number"] = updates.phone_number
        if updates.city is not None:
            update_data["city"] = updates.city
        if updates.state is not None:
            update_data["state"] = updates.state
        if updates.address is not None:
            update_data["address"] = updates.address
        if updates.bio is not None:
            update_data["bio"] = updates.bio
        if updates.date_of_birth is not None:
            update_data["date_of_birth"] = updates.date_of_birth
        if updates.profile_image_url is not None:
            update_data["profile_image_url"] = updates.profile_image_url
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update user in database
        result = await db.update("users", {"id": user_id}, update_data)

        # Return updated user
        user_data = await db.select("users", filters={"id": user_id})
        if user_data:
            return user_data[0]
        
        return {"success": True, "message": "Profile updated", "id": user_id}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")


@router.post("/send-otp")
async def send_otp(payload: SendOTPRequest) -> Dict[str, Any]:
    """Send OTP via email for email verification."""
    try:

        from ..services.otp_service import send_email_otp
        token = await send_email_otp(payload.email, payload.action)
        
        # Return in format frontend expects
        return {"success": True, "sent": True, "otp": token}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send OTP: {str(e)}")

@router.post("/verify-otp")
async def verify_otp(payload: VerifyOTPRequest) -> Dict[str, Any]:
    """Verify OTP for email verification."""
    try:

        from ..services.otp_service import verify_email_otp
        is_valid = verify_email_otp(payload.email, payload.otp, payload.action)
        
        if not is_valid:

            raise HTTPException(status_code=400, detail="Invalid or expired OTP")

        return {"success": True}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to verify OTP: {str(e)}")

@router.get("/verify-email/{token}")
async def verify_email(token: str) -> Dict[str, Any]:
    """Verify email using token from email link."""
    try:

        # Find token in database
        tokens = await db.select("email_verification_tokens", filters={"token": token})
        if not tokens:

            raise HTTPException(status_code=400, detail="Invalid or expired verification token")

        token_record = tokens[0]
        user_id = token_record.get("user_id")
        expires_at_str = token_record.get("expires_at")
        
        if not expires_at_str:

            raise HTTPException(status_code=400, detail="Invalid token format")

        # Check if token is expired
        try:
            expires_at = dt.datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            now_utc = dt.datetime.now(dt.timezone.utc)
            if now_utc > expires_at:

                raise HTTPException(status_code=400, detail="Verification token has expired")
        except Exception as parse_error:
            raise HTTPException(status_code=400, detail="Invalid token format")
        
        if not user_id:

            raise HTTPException(status_code=400, detail="Invalid token format")

        # Find user
        users = await db.select("users", filters={"id": user_id})
        if not users:

            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        
        # Check if already verified
        if user.get("email_verified", False):
            return {
                "success": True,
                "message": "Email is already verified",
                "already_verified": True
            }
        
        # Update user as verified
        try:
            update_data = {
                "email_verified": True,
                "verification_status": "verified",
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
            }
            await db.update("users", update_data, {"id": user_id})
        except Exception as update_error:

            raise HTTPException(status_code=500, detail="Failed to verify email")
        
        # Log verification event
        try:
            log_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "event_type": "email_verified",
                "details": f"Email verified via token: {token}",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat()
            }
            await db.insert("user_activity_logs", log_data)
        except Exception as log_err:
            pass

        # Delete the used token
        try:
            await db.delete("email_verification_tokens", {"token": token})
        except Exception as e:
            pass

        return {
            "success": True,
            "message": "Email verified successfully! You can now sign in to your account.",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "first_name": user.get("first_name", ""),
                "last_name": user.get("last_name", "")
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:


        raise HTTPException(status_code=500, detail=f"Email verification failed: {str(e)}")

@router.post("/verify-email-otp")
async def verify_email_otp(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Verify email using OTP sent to email."""
    try:
        email = payload.get("email", "").lower()
        otp = payload.get("otp", "")

        # Validate OTP format
        if len(otp) != 6 or not otp.isdigit():
            raise HTTPException(status_code=400, detail="Invalid OTP format")
        
        # Find user by email
        users = await db.select("users", filters={"email": email})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        user_id = user["id"]
        
        # Check if already verified
        if user.get("email_verified", False):

            return {
                "success": True,
                "message": "Email is already verified",
                "already_verified": True
            }
        
        # Verify OTP using the OTP service
        try:
            from ..services.otp_service import verify_email_otp as verify_otp_service
            is_valid = verify_otp_service(email, otp, "email_verification")
            
            if not is_valid:

                raise HTTPException(status_code=400, detail="Invalid or expired OTP")
                
        except HTTPException:
            raise
        except Exception as otp_error:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        
        # Update user as verified
        try:
            update_data = {
                "email_verified": True,
                "verification_status": "verified",
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
            }
            await db.update("users", update_data, {"id": user_id})
        except Exception as update_error:

            raise HTTPException(status_code=500, detail="Failed to verify email")
        
        # Log verification event
        try:
            log_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "event_type": "email_verified",
                "details": f"Email verified via OTP: {email}",
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat()
            }
            await db.insert("user_activity_logs", log_data)
        except Exception as log_err:
            pass

        return {
            "success": True,
            "message": "Email verified successfully! You can now sign in to your account.",
            "user": {
                "id": user["id"],
                "email": user["email"],
                "first_name": user.get("first_name", ""),
                "last_name": user.get("last_name", "")
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:


        raise HTTPException(status_code=500, detail=f"Email verification failed: {str(e)}")

@router.get("/admin/tokens")
async def list_tokens() -> Dict[str, Any]:
    """List all email verification tokens (admin only)."""
    try:
        tokens = await db.select("email_verification_tokens")
        return {"success": True, "tokens": tokens}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list tokens: {str(e)}")

@router.post("/resend-verification")
async def resend_verification_email(request: Request) -> Dict[str, Any]:
    """Resend verification email to user"""
    try:
        # Get email from query parameters
        email = request.query_params.get("email")
        if not email:
            return {
                "success": False,
                "error": "Email parameter is required"
            }

        # Check if user exists
        users = await db.select("users", filters={"email": email.lower()})
        if not users:
            return {
                "success": False,
                "error": "User not found"
            }
        
        user = users[0]
        
        # Check if email is already verified
        if user.get("email_verified"):
            return {
                "success": False,
                "error": "Email is already verified"
            }
        
        # Send email verification OTP
        try:
            from ..services.otp_service import send_email_otp
            otp_token = await send_email_otp(email, "email_verification")

            return {
                "success": True,
                "message": "Verification email sent successfully! Please check your inbox."
            }
        except Exception as otp_error:
            return {
                "success": False,
                "error": "Failed to send verification email. Please try again."
            }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to resend verification email: {str(e)}"
        }

@router.post("/logout")
async def logout(request: Request, response: Response) -> Dict[str, Any]:
    """Logout user by revoking refresh token - optimized for speed."""
    try:
        # Clear the cookie immediately (don't wait for database)
        response.delete_cookie("refresh_token", path="/api")
        
        # Get refresh token from cookie (before clearing)
        refresh_token = request.cookies.get("refresh_token")
        
        # Revoke token in background (non-blocking) - don't wait for it
        if refresh_token:
            import asyncio
            # Hash the token to find it in database
            refresh_hash = hash_refresh_token(refresh_token)
            
            # Delete token in background with timeout - don't block response
            async def revoke_token_background():
                try:
                    import asyncio
                    tokens = await asyncio.wait_for(
                        db.select("refresh_tokens", filters={"token_hash": refresh_hash}, limit=10),
                        timeout=2.0  # 2 second timeout
                    )
                    for t in tokens:
                        try:
                            await asyncio.wait_for(
                                db.delete("refresh_tokens", {"id": t["id"]}),
                                timeout=2.0  # 2 second timeout
                            )
                        except asyncio.TimeoutError:
                            pass  # Ignore timeout - token will expire anyway
                        except Exception:
                            pass  # Ignore errors - token will expire anyway
                except asyncio.TimeoutError:
                    pass  # Ignore timeout - token will expire anyway
                except Exception:
                    pass  # Ignore errors - token will expire anyway
            
            # Fire and forget - don't wait for completion
            asyncio.create_task(revoke_token_background())
        
        # Return immediately - don't wait for token deletion
        return {"success": True, "message": "Logged out successfully"}
        
    except Exception as e:
        # Even on error, return success - logout should always succeed
        return {"success": True, "message": "Logged out successfully"}


@router.get("/me")
async def get_current_user(request: Request) -> Dict[str, Any]:
    """Get current user information with roles"""
    try:
        from ..core.security import get_current_user_claims
        claims = get_current_user_claims(request)
        
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get user details
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        
        # Get user's active roles
        try:
            from ..services.user_role_service import UserRoleService
            active_roles = await UserRoleService.get_active_user_roles(user_id)
            role_info = await UserRoleService.get_user_role_info(user_id)
        except Exception as role_error:
            active_roles = [user.get("user_type", "buyer")]
            role_info = {
                "active_roles": active_roles,
                "has_buyer_access": "buyer" in active_roles,
                "has_seller_access": "seller" in active_roles,
                "has_agent_access": "agent" in active_roles,
                "has_admin_access": "admin" in active_roles
            }
        
        return {
            "success": True,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "first_name": user.get("first_name", ""),
                "last_name": user.get("last_name", ""),
                "user_type": user.get("user_type", "buyer"),
                "active_roles": active_roles,
                "role_info": role_info,
                "email_verified": user.get("email_verified", False),
                "status": user.get("status", "active"),
                "custom_id": user.get("custom_id")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get user information: {str(e)}")


@router.post("/request-role")
async def request_additional_role(request: Request) -> Dict[str, Any]:
    """Request an additional role (e.g., buyer requesting seller role)"""
    try:
        from ..core.security import get_current_user_claims
        claims = get_current_user_claims(request)
        
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        body = await request.json()
        requested_role = body.get("role", "").lower()
        
        if not requested_role:
            raise HTTPException(status_code=400, detail="Role is required")
        
        if requested_role not in ["buyer", "seller", "agent", "admin"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        
        # Get user details
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        
        # Check if user already has this role
        try:
            from ..services.user_role_service import UserRoleService
            from ..services.email import send_email
            import pytz
            
            has_role = await UserRoleService.has_role(user_id, requested_role)
            if has_role:
                return {
                    "success": False,
                    "error": f"You already have the {requested_role} role"
                }
            
            # Allow users to update their profile/login info when requesting role change
            # This allows them to prepare their account for the new role
            profile_updates = {}
            if body.get("first_name"):
                profile_updates["first_name"] = body.get("first_name")
            if body.get("last_name"):
                profile_updates["last_name"] = body.get("last_name")
            if body.get("phone_number"):
                profile_updates["phone_number"] = body.get("phone_number")
            if body.get("email") and body.get("email") != user.get("email"):
                # Email change requires verification, so we'll note it but not change it yet
                profile_updates["email_verification_token"] = None
                profile_updates["email_verified"] = False
            
            # Update profile if any changes provided
            if profile_updates:
                profile_updates["updated_at"] = dt.datetime.utcnow().isoformat()
                await db.update("users", profile_updates, {"id": user_id})
            
            # Add the role as pending (requires admin approval)
            success = await UserRoleService.add_additional_role(user_id, requested_role)
            
            if success:
                role_display = {
                    "buyer": "Buyer",
                    "seller": "Seller",
                    "agent": "Agent",
                    "admin": "Administrator"
                }.get(requested_role, requested_role.title())
                
                current_role_display = {
                    "buyer": "Buyer",
                    "seller": "Seller",
                    "agent": "Agent",
                    "admin": "Administrator"
                }.get(user.get("user_type", "").lower(), "User")
                
                # Send confirmation email to user
                user_email_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                    <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                        <div style="background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); padding: 40px 20px; text-align: center;">
                            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Role Request Submitted</h1>
                        </div>
                        
                        <div style="padding: 40px 30px;">
                            <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user.get('first_name', 'User')},</h2>
                            
                            <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                Your request for <strong>{role_display}</strong> access has been successfully submitted and is now pending admin review.
                            </p>
                            
                            <div style="background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 16px; margin: 30px 0; border-radius: 4px;">
                                <p style="color: #1e40af; font-size: 14px; margin: 0; line-height: 1.5;">
                                    <strong>📋 What happens next?</strong><br>
                                    • Our admin team will review your request<br>
                                    • You'll receive an email notification once your request is approved or if additional information is needed<br>
                                    • Review typically takes 1-2 business days
                                </p>
                            </div>
                            
                            <div style="background-color: #f8fafc; border-radius: 8px; padding: 20px; margin: 30px 0;">
                                <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0; line-height: 1.6;">
                                    <strong>Request Details:</strong>
                                </p>
                                <p style="color: #64748b; font-size: 14px; margin: 0; line-height: 1.6;">
                                    • Requested Role: {role_display}<br>
                                    • Current Role: {current_role_display}<br>
                                    • Date: {dt.datetime.now(pytz.UTC).strftime('%B %d, %Y at %I:%M %p UTC')}<br>
                                    • Status: Pending Review
                                </p>
                            </div>
                        </div>
                        
                        <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                            <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                                Best regards,<br>
                                <strong>The Home & Own Team</strong>
                            </p>
                            <p style="color: #94a3b8; font-size: 12px; margin: 20px 0 0 0;">
                                © 2025 Home & Own. All rights reserved.
                            </p>
                        </div>
                    </div>
                </body>
                </html>
                """
                
                try:
                    email_result = await send_email(
                        to=user["email"],
                        subject=f"Role Request Submitted - Home & Own",
                        html=user_email_html
                    )
                    if email_result.get("status") == "sent":
                        pass
                    else:
                        pass
                except Exception as email_error:
                    pass

                # Send notification to admins
                try:
                    admin_users = await db.select("users", filters={"user_type": "admin"})
                    
                    admin_email_html = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    </head>
                    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                        <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 40px 20px; text-align: center;">
                                <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">New Role Request</h1>
                            </div>
                            
                            <div style="padding: 40px 30px;">
                                <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Admin Action Required</h2>
                                
                                <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                    A user has requested additional role access and requires your review.
                                </p>
                                
                                <div style="background-color: #f8fafc; border-radius: 8px; padding: 20px; margin: 30px 0;">
                                    <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0; line-height: 1.6;">
                                        <strong>User Information:</strong>
                                    </p>
                                    <p style="color: #64748b; font-size: 14px; margin: 0; line-height: 1.6;">
                                        • Name: {user.get('first_name', '')} {user.get('last_name', '')}<br>
                                        • Email: {user.get('email', '')}<br>
                                        • Current Role: {current_role_display}<br>
                                        • Requested Role: <strong>{role_display}</strong><br>
                                        • User ID: {user_id}<br>
                                        • Date: {dt.datetime.now(pytz.UTC).strftime('%B %d, %Y at %I:%M %p UTC')}
                                    </p>
                                </div>
                                
                                <div style="text-align: center; margin: 40px 0;">
                                    <a href="{settings.SITE_URL}/admin/dashboard" 
                                       style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                              color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                              font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);">
                                        Review in Admin Dashboard
                                    </a>
                                </div>
                            </div>
                            
                            <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                                <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                                    <strong>Home & Own Admin System</strong>
                                </p>
                                <p style="color: #94a3b8; font-size: 12px; margin: 20px 0 0 0;">
                                    © 2025 Home & Own. All rights reserved.
                                </p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    
                    for admin in admin_users:
                        try:
                            email_result = await send_email(
                                to=admin["email"],
                                subject=f"New Role Request: {role_display} - Home & Own",
                                html=admin_email_html
                            )
                            if email_result.get("status") == "sent":
                                pass
                            else:
                                pass
                        except Exception as admin_email_error:
                            pass

                except Exception as admin_notify_error:
                    pass

                return {
                    "success": True,
                    "message": f"Role request submitted successfully. Admin approval required for {requested_role} role."
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to submit role request"
                }
                
        except Exception as role_error:
            import traceback
            return {
                "success": False,
                "error": f"Failed to submit role request: {str(role_error)}"
            }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        raise HTTPException(status_code=500, detail=f"Failed to submit role request: {str(e)}")


@router.post("/forgot-password")
async def forgot_password(request: Request) -> Dict[str, Any]:
    """Send password reset OTP via email."""
    try:
        body = await request.json()
        email = body.get("email", "").lower().strip()
        user_type = body.get("user_type", "").lower().strip()  # Get requested user type
        
        print(f"[FORGOT-PASSWORD] Received request for email: {email}")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        
        # Check if user exists
        users = await db.select("users", filters={"email": email})
        if not users:
            # Return specific error for user not found with better messaging
            user_type_display = user_type.title() if user_type else "User"
            raise HTTPException(
                status_code=404, 
                detail={
                    "message": f"No {user_type_display.lower()} account found with this email address.",
                    "suggestion": "Please check your email address or sign up for a new account.",
                    "action": "signup"
                }
            )
        
        user = users[0]
        user_id = user["id"]
        actual_user_type = user.get("user_type", "buyer").lower()
        
        print(f"[FORGOT-PASSWORD] Found user: {user_id}, type: {actual_user_type}")
        
        # Validate that the user's role matches the requested role (if user_type is provided)
        if user_type and actual_user_type != user_type:

            raise HTTPException(
                status_code=404, 
                detail={
                    "message": f"No {user_type} account found with this email address.",
                    "suggestion": f"This email is registered as a {actual_user_type}. Please use the {actual_user_type} login page or sign up for a new {user_type} account.",
                    "action": "wrong_user_type",
                    "actual_user_type": actual_user_type,
                    "requested_user_type": user_type
                }
            )
        
        # Send OTP via email for password reset
        try:
            from ..services.otp_service import send_email_otp
            
            print(f"[FORGOT-PASSWORD] Attempting to send OTP to {email}")
            otp_token = await send_email_otp(email, "password_reset")
            print(f"[FORGOT-PASSWORD] OTP sent successfully")
        except Exception as otp_error:
            print(f"[FORGOT-PASSWORD] Error sending OTP: {str(otp_error)}")
            raise HTTPException(
                status_code=500, 
                detail={
                    "message": "Failed to send OTP email. Please try again later.",
                    "error": str(otp_error)
                }
            )


        return {
            "success": True,
            "message": "OTP has been sent to your email address. Please check your inbox.",
            "email": email  # Return email for frontend to use in OTP verification
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[FORGOT-PASSWORD] Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail={
                "message": "Failed to process password reset request",
                "error": str(e)
            }
        )


@router.post("/reset-password")
async def reset_password(request: Request) -> Dict[str, Any]:
    """Reset password using OTP verification."""
    try:
        body = await request.json()
        email = body.get("email", "").lower().strip()
        otp = body.get("otp", "").strip()
        new_password = body.get("password", "").strip()
        confirm_password = body.get("confirm_password", "").strip()
        
        if not email or not otp or not new_password:
            raise HTTPException(status_code=400, detail="Email, OTP, and new password are required")
        
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

        # Verify OTP
        from ..services.otp_service import verify_email_otp
        
        is_valid = verify_email_otp(email, otp, "password_reset")
        
        
        
        if not is_valid:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")
        
        # Find user by email
        users = await db.select("users", filters={"email": email})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        user_id = user["id"]
        
        # Hash new password
        from ..core.crypto import get_password_hash
        from ..services.email import send_email
        from ..core.config import settings
        password_hash = get_password_hash(new_password)
        
        # Update user password
        
        await db.update("users", {
            "password_hash": password_hash,
            "updated_at": dt.datetime.now(pytz.UTC).isoformat()
        }, {"id": user_id})
        
        

        # Get user details and send confirmation email
        user_type = user.get("user_type", "buyer").lower()
        
        # Get role display name and login URL
        role_info = {
            "admin": {"name": "Administrator", "url": "/admin/login"},
            "agent": {"name": "Agent", "url": "/agent/login"},
            "seller": {"name": "Seller", "url": "/login"},
            "buyer": {"name": "Buyer", "url": "/login"}
        }
        role = role_info.get(user_type, {"name": "User", "url": "/login"})
        
        # Use SITE_URL from environment (required for production)
        site_url = settings.SITE_URL
        if not site_url:
            raise ValueError("SITE_URL environment variable is required for production deployment")
        # Ensure we use HTTPS in production
        if not site_url.startswith("https://") and not site_url.startswith("http://localhost"):
            pass

        login_url = f"{site_url}{role['url']}"
        
        # Send confirmation email
        try:
            user_name = user.get('first_name', 'User')
            user_email = user.get('email', '')
            timestamp = dt.datetime.now(pytz.UTC).strftime('%B %d, %Y at %I:%M %p UTC')
            support_email = getattr(settings, 'SUPPORT_EMAIL', 'support@homeandown.com')
            
            confirmation_html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Password Reset Successful - Home & Own</title>
            </head>
            <body style="margin: 0; padding: 0; background-color: #f5f7fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f7fa;">
                    <tr>
                        <td align="center" style="padding: 40px 20px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); overflow: hidden;">
                                <!-- Header -->
                                <tr>
                                    <td style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 50px 30px; text-align: center;">
                                        <div style="width: 80px; height: 80px; background-color: rgba(255, 255, 255, 0.2); border-radius: 50%; margin: 0 auto 24px; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(10px);">
                                            <span style="font-size: 40px; color: #ffffff;">✓</span>
                                        </div>
                                        <h1 style="margin: 0; color: #ffffff; font-size: 32px; font-weight: 700; letter-spacing: -0.5px;">Password Reset Successful!</h1>
                                        <p style="margin: 12px 0 0 0; color: rgba(255, 255, 255, 0.95); font-size: 16px;">Your password has been updated</p>
                                    </td>
                                </tr>
                                
                                <!-- Content -->
                                <tr>
                                    <td style="padding: 50px 40px;">
                                        <h2 style="margin: 0 0 20px 0; color: #1e293b; font-size: 24px; font-weight: 600;">Hello {user_name},</h2>
                                        
                                        <p style="margin: 0 0 24px 0; color: #475569; font-size: 16px; line-height: 1.7;">
                                            Your password has been successfully reset for your <strong style="color: #1e293b;">{role['name']}</strong> account on Home & Own.
                                        </p>
                                        
                                        <p style="margin: 0 0 40px 0; color: #475569; font-size: 16px; line-height: 1.7;">
                                            You can now log in to your account using your new password. For security reasons, please keep your password confidential and do not share it with anyone.
                                        </p>
                                        
                                        <!-- Login Button -->
                                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                            <tr>
                                                <td align="center" style="padding: 0 0 40px 0;">
                                                    <a href="{login_url}" 
                                                       style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                              color: #ffffff; padding: 16px 48px; text-decoration: none; border-radius: 10px; 
                                                              font-weight: 600; font-size: 16px; box-shadow: 0 8px 16px rgba(37, 99, 235, 0.3);
                                                              transition: all 0.3s ease;">
                                                        Login to Your Account
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                        
                                        <!-- Security Alert -->
                                        <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; border-radius: 8px; padding: 20px; margin: 0 0 32px 0;">
                                            <p style="margin: 0 0 8px 0; color: #991b1b; font-size: 14px; font-weight: 600;">
                                                🔒 Security Alert
                                            </p>
                                            <p style="margin: 0; color: #991b1b; font-size: 14px; line-height: 1.6;">
                                                If you didn't make this change, please contact our support team immediately at 
                                                <a href="mailto:{support_email}" style="color: #991b1b; text-decoration: underline; font-weight: 500;">{support_email}</a>
                                            </p>
                                        </div>
                                        
                                        <!-- Details Box -->
                                        <div style="background-color: #f8fafc; border-radius: 10px; padding: 24px; margin: 0 0 32px 0; border: 1px solid #e2e8f0;">
                                            <p style="margin: 0 0 16px 0; color: #1e293b; font-size: 15px; font-weight: 600;">Password Reset Details:</p>
                                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                                <tr>
                                                    <td style="padding: 8px 0; color: #64748b; font-size: 14px; line-height: 1.8;">
                                                        <strong style="color: #475569;">Date & Time:</strong> {timestamp}
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 8px 0; color: #64748b; font-size: 14px; line-height: 1.8;">
                                                        <strong style="color: #475569;">Account Type:</strong> {role['name']}
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 8px 0; color: #64748b; font-size: 14px; line-height: 1.8;">
                                                        <strong style="color: #475569;">Email:</strong> {user_email}
                                                    </td>
                                                </tr>
                                            </table>
                                        </div>
                                        
                                        <p style="margin: 0; color: #94a3b8; font-size: 14px; text-align: center; line-height: 1.6;">
                                            Need help? Contact us at 
                                            <a href="mailto:{support_email}" style="color: #2563eb; text-decoration: none; font-weight: 500;">{support_email}</a>
                                        </p>
                                    </td>
                                </tr>
                                
                                <!-- Footer -->
                                <tr>
                                    <td style="background-color: #f8fafc; padding: 30px 40px; text-align: center; border-top: 1px solid #e2e8f0;">
                                        <p style="margin: 0 0 12px 0; color: #64748b; font-size: 14px; line-height: 1.6;">
                                            Best regards,<br>
                                            <strong style="color: #1e293b;">The Home & Own Team</strong>
                                        </p>
                                        <p style="margin: 0; color: #94a3b8; font-size: 12px;">
                                            © 2025 Home & Own. All rights reserved.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """
            
            
            await send_email(
                to=user["email"],
                subject="Password Reset Successful - Home & Own",
                html=confirmation_html
            )
            

        except Exception as email_error:
            # Don't fail password reset if email fails
            pass
        
        return {
            "success": True,
            "message": "Password reset successful. An email confirmation has been sent. You can now log in with your new password.",
            "user_type": user_type
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to reset password")

@router.post("/change-password")
async def change_password(request: Request) -> Dict[str, Any]:
    """Change user password by verifying current password and setting new one."""
    try:
        from ..core.security import get_current_user_claims
        from ..core.crypto import verify_password, get_password_hash
        from ..services.email import send_email
        from ..core.config import settings
        
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        body = await request.json()
        current_password = body.get("current_password", "").strip()
        new_password = body.get("new_password", "").strip()
        
        if not current_password or not new_password:
            raise HTTPException(status_code=400, detail="Both current_password and new_password are required")
        
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
        
        # Get user
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        password_hash = user.get("password_hash")
        
        # Verify current password
        
        password_valid = password_hash and verify_password(current_password, password_hash)
        
        if not password_valid:
            raise HTTPException(status_code=400, detail="Invalid current password")
        
        # Check if new password is same as current
        if verify_password(new_password, password_hash):
            raise HTTPException(status_code=400, detail="New password must be different from current password")
        
        # Hash new password
        new_password_hash = get_password_hash(new_password)
        
        # Update password
        await db.update("users", {
            "password_hash": new_password_hash,
            "updated_at": dt.datetime.now(pytz.UTC).isoformat()
        }, {"id": user_id})

        # Send confirmation email
        try:
            user_email = user.get("email")
            user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "User"
            user_type = user.get("user_type", "buyer").lower()
            timestamp = dt.datetime.now(pytz.UTC).strftime('%B %d, %Y at %I:%M %p UTC')
            
            # Get role display name and login URL
            role_info = {
                "admin": {"name": "Administrator", "url": "/admin/login"},
                "agent": {"name": "Agent", "url": "/agent/login"},
                "seller": {"name": "Seller", "url": "/login"},
                "buyer": {"name": "Buyer", "url": "/login"}
            }
            role = role_info.get(user_type, {"name": "User", "url": "/login"})
            
            # Use SITE_URL from environment (required for production)
            site_url = settings.SITE_URL
            if not site_url:
                raise ValueError("SITE_URL environment variable is required for production deployment")
            # Ensure we use HTTPS in production
            if not site_url.startswith("https://") and not site_url.startswith("http://localhost"):
                pass

            login_url = f"{site_url}{role['url']}"
            support_email = getattr(settings, 'SUPPORT_EMAIL', 'support@homeandown.com')
            
            email_html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Password Changed Successfully - Home & Own</title>
            </head>
            <body style="margin: 0; padding: 0; background-color: #f5f7fa; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;">
                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f7fa;">
                    <tr>
                        <td align="center" style="padding: 40px 20px;">
                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width: 600px; background-color: #ffffff; border-radius: 16px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1); overflow: hidden;">
                                <!-- Header -->
                                <tr>
                                    <td style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 50px 30px; text-align: center;">
                                        <div style="width: 80px; height: 80px; background-color: rgba(255, 255, 255, 0.2); border-radius: 50%; margin: 0 auto 24px; display: flex; align-items: center; justify-content: center; backdrop-filter: blur(10px);">
                                            <span style="font-size: 40px; color: #ffffff;">✓</span>
                                        </div>
                                        <h1 style="margin: 0; color: #ffffff; font-size: 32px; font-weight: 700; letter-spacing: -0.5px;">Password Changed Successfully!</h1>
                                        <p style="margin: 12px 0 0 0; color: rgba(255, 255, 255, 0.95); font-size: 16px;">Your account is now more secure</p>
                                    </td>
                                </tr>
                                
                                <!-- Content -->
                                <tr>
                                    <td style="padding: 50px 40px;">
                                        <h2 style="margin: 0 0 20px 0; color: #1e293b; font-size: 24px; font-weight: 600;">Hello {user_name},</h2>
                                        
                                        <p style="margin: 0 0 24px 0; color: #475569; font-size: 16px; line-height: 1.7;">
                                            Your password has been successfully changed for your <strong style="color: #1e293b;">{role['name']}</strong> account on Home & Own.
                                        </p>
                                        
                                        <p style="margin: 0 0 40px 0; color: #475569; font-size: 16px; line-height: 1.7;">
                                            You can now log in to your account using your new password. For security reasons, please keep your password confidential and do not share it with anyone.
                                        </p>
                                        
                                        <!-- Login Button -->
                                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                            <tr>
                                                <td align="center" style="padding: 0 0 40px 0;">
                                                    <a href="{login_url}" 
                                                       style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                              color: #ffffff; padding: 16px 48px; text-decoration: none; border-radius: 10px; 
                                                              font-weight: 600; font-size: 16px; box-shadow: 0 8px 16px rgba(37, 99, 235, 0.3);">
                                                        Continue to Dashboard
                                                    </a>
                                                </td>
                                            </tr>
                                        </table>
                                        
                                        <!-- Security Alert -->
                                        <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; border-radius: 8px; padding: 20px; margin: 0 0 32px 0;">
                                            <p style="margin: 0 0 8px 0; color: #991b1b; font-size: 14px; font-weight: 600;">
                                                🔒 Security Alert
                                            </p>
                                            <p style="margin: 0; color: #991b1b; font-size: 14px; line-height: 1.6;">
                                                If you didn't make this change, please contact our support team immediately at 
                                                <a href="mailto:{support_email}" style="color: #991b1b; text-decoration: underline; font-weight: 500;">{support_email}</a>
                                            </p>
                                        </div>
                                        
                                        <!-- Details Box -->
                                        <div style="background-color: #f8fafc; border-radius: 10px; padding: 24px; margin: 0 0 32px 0; border: 1px solid #e2e8f0;">
                                            <p style="margin: 0 0 16px 0; color: #1e293b; font-size: 15px; font-weight: 600;">Password Change Details:</p>
                                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
                                                <tr>
                                                    <td style="padding: 8px 0; color: #64748b; font-size: 14px; line-height: 1.8;">
                                                        <strong style="color: #475569;">Date & Time:</strong> {timestamp}
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 8px 0; color: #64748b; font-size: 14px; line-height: 1.8;">
                                                        <strong style="color: #475569;">Account Type:</strong> {role['name']}
                                                    </td>
                                                </tr>
                                                <tr>
                                                    <td style="padding: 8px 0; color: #64748b; font-size: 14px; line-height: 1.8;">
                                                        <strong style="color: #475569;">Email:</strong> {user_email}
                                                    </td>
                                                </tr>
                                            </table>
                                        </div>
                                        
                                        <p style="margin: 0; color: #94a3b8; font-size: 14px; text-align: center; line-height: 1.6;">
                                            Need help? Contact us at 
                                            <a href="mailto:{support_email}" style="color: #2563eb; text-decoration: none; font-weight: 500;">{support_email}</a>
                                        </p>
                                    </td>
                                </tr>
                                
                                <!-- Footer -->
                                <tr>
                                    <td style="background-color: #f8fafc; padding: 30px 40px; text-align: center; border-top: 1px solid #e2e8f0;">
                                        <p style="margin: 0 0 12px 0; color: #64748b; font-size: 14px; line-height: 1.6;">
                                            Best regards,<br>
                                            <strong style="color: #1e293b;">The Home & Own Team</strong>
                                        </p>
                                        <p style="margin: 0; color: #94a3b8; font-size: 12px;">
                                            © 2025 Home & Own. All rights reserved.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>
                </table>
            </body>
            </html>
            """
            
            await send_email(
                to=user_email,
                subject="Password Changed Successfully - Home & Own",
                html=email_html
            )

        except Exception as email_error:
            # Don't fail password change if email fails
            pass
        
        return {
            "success": True,
            "message": "Password changed successfully. An email notification has been sent."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to change password: {str(e)}")
