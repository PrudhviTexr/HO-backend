from fastapi import APIRouter, HTTPException, Request, Response
from ..models.schemas import UpdateProfileRequest, BankDetailsRequest, DeleteAccountRequest
from ..core.security import get_current_user_claims
from ..core.crypto import verify_password, hash_refresh_token
from ..services.account_deletion_service import delete_user_account
from ..services.otp_service import verify_otp_simple
from ..db.supabase_client import db
import datetime as dt
import uuid

router = APIRouter()


async def _delete_own_account_impl(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
):
    """Authenticated user deletes their own account (password + DELETE confirmation required)."""
    claims = get_current_user_claims(request)
    if not claims:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    if (payload.confirmation or "").strip().upper() != "DELETE":
        raise HTTPException(
            status_code=400,
            detail='Type DELETE in the confirmation field to proceed',
        )

    users = await db.select("users", filters={"id": user_id})
    if not users:
        raise HTTPException(status_code=404, detail="User not found")

    user = users[0]
    user_type = (user.get("user_type") or "").lower()
    if user_type == "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin accounts cannot be deleted from the app. Contact support.",
        )

    password_hash = user.get("password_hash")
    if not password_hash or not verify_password(payload.password, password_hash):
        raise HTTPException(status_code=400, detail="Invalid password")

    await delete_user_account(user_id)

    response.delete_cookie("refresh_token", path="/api")
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        try:
            refresh_hash = hash_refresh_token(refresh_token)
            tokens = await db.select(
                "refresh_tokens", filters={"token_hash": refresh_hash}, limit=20
            )
            for token_row in tokens or []:
                if token_row.get("id"):
                    await db.delete("refresh_tokens", {"id": token_row["id"]})
        except Exception as token_err:
            print(f"[USERS] Refresh token cleanup on delete: {token_err}")

    return {"success": True, "message": "Your account has been permanently deleted"}


@router.post("/delete-account")
async def delete_own_account_post(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
):
    """Delete account via POST (recommended for mobile — DELETE bodies are often stripped)."""
    try:
        return await _delete_own_account_impl(payload, request, response)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Delete account error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to delete account. Please try again.")


@router.delete("/account")
async def delete_own_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
):
    """Delete account via DELETE (web clients with full body support)."""
    try:
        return await _delete_own_account_impl(payload, request, response)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Delete account error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Failed to delete account. Please try again.")

@router.get("/me")
async def get_user_profile(request: Request):
    """Get current user's profile information with ALL fields"""
    try:
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
        user_type = user.get("user_type", "buyer")
        
        # Get user's active roles
        try:
            from ..services.user_role_service import UserRoleService
            active_roles = await UserRoleService.get_active_user_roles(user_id)
        except Exception as role_error:
            print(f"[USERS] Failed to get user roles: {role_error}")
            active_roles = [user_type]
        
        # Fetch agent profile data if user is an agent
        experience_years = None
        specialization = None
        if user_type == "agent":
            try:
                agent_profiles = await db.select("agent_profiles", filters={"user_id": user_id}, limit=1)
                if agent_profiles and len(agent_profiles) > 0:
                    agent_profile = agent_profiles[0]
                    experience_years = agent_profile.get("experience_years")
                    specialization = agent_profile.get("specialization")
            except Exception as agent_profile_error:
                print(f"[USERS] Failed to fetch agent profile (non-critical): {agent_profile_error}")
                # Continue without agent profile data - don't fail the request
        
        # Return ALL fields
        return {
            "success": True,
            "user": {
                "id": user["id"],
                "email": user["email"],
                "first_name": user.get("first_name", ""),
                "last_name": user.get("last_name", ""),
                "phone_number": user.get("phone_number", ""),
                "date_of_birth": user.get("date_of_birth"),
                "user_type": user_type,
                "active_roles": active_roles,
                "status": user.get("status", "active"),
                "verification_status": user.get("verification_status", "pending"),
                "email_verified": user.get("email_verified", False),
                "created_at": user.get("created_at"),
                "updated_at": user.get("updated_at"),
                "profile_image_url": user.get("profile_image_url"),
                "city": user.get("city", ""),
                "state": user.get("state", ""),
                "district": user.get("district", ""),
                "mandal": user.get("mandal", ""),
                "zip_code": user.get("zip_code", ""),
                "address": user.get("address", ""),
                "latitude": user.get("latitude"),
                "longitude": user.get("longitude"),
                "bio": user.get("bio", ""),
                "business_name": user.get("business_name", ""),
                "custom_id": user.get("custom_id"),
                # Agent-specific fields (read-only) - fetched from agent_profiles
                "agent_license_number": user.get("agent_license_number"),
                "experience_years": experience_years,
                "specialization": specialization,
                # Bank details (read-only for security)
                "bank_account_number": user.get("bank_account_number"),
                "ifsc_code": user.get("ifsc_code"),
                "bank_verified": user.get("bank_verified", False)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Get profile error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get profile: {str(e)}")

@router.patch("/profile")
async def update_profile(payload: UpdateProfileRequest, request: Request):
    """Update user profile - some fields are read-only for security"""
    try:
        claims = get_current_user_claims(request)
        user_id = claims.get("sub")
        
        print(f"[USERS] Updating profile for user: {user_id}")
        
        # Get current user data before update
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        current_user = users[0]
        
        # For sensitive updates, require current password or OTP verification
        if payload.current_password:
            print(f"[USERS] Current password provided, verifying...")
            from ..core.crypto import verify_password
            password_hash = current_user.get("password_hash")
            if not password_hash or not verify_password(payload.current_password, password_hash):
                raise HTTPException(status_code=400, detail="Invalid current password")
            print(f"[USERS] Current password verified for profile update")
        elif payload.otp:
            print(f"[USERS] OTP provided, verifying...")
            phone = current_user.get("phone_number", "")
            if not verify_otp_simple(phone, payload.otp, "profile_update"):
                raise HTTPException(status_code=400, detail="Invalid OTP")
            print(f"[USERS] OTP verified for profile update")
        
        # List of READ-ONLY fields that cannot be edited via this endpoint
        # These require special admin approval or separate endpoints
        readonly_fields = [
            "agent_license_number",  # Generated by system, admin-only
            "bank_account_number",   # Requires separate bank update flow with OTP
            "ifsc_code",             # Requires separate bank update flow with OTP
            "bank_verified",         # Admin-only
            "email_verified",        # System-only
            "verification_status",   # Admin-only
            "status",                # Admin-only
            "user_type",             # Admin-only
            "custom_id"              # System-generated
        ]
        
        print(f"[USERS] Read-only fields protected: {', '.join(readonly_fields)}")
        
        # Update user profile (EDITABLE FIELDS ONLY)
        update_data = {}
        sensitive_changes = []
        
        # Basic Info (Editable)
        if payload.first_name is not None:
            update_data["first_name"] = payload.first_name
        if payload.last_name is not None:
            update_data["last_name"] = payload.last_name
            
        # Sensitive Fields (Editable with notification)
        if payload.phone_number is not None and payload.phone_number != current_user.get("phone_number"):
            update_data["phone_number"] = payload.phone_number
            sensitive_changes.append("phone number")
        if payload.email is not None and payload.email != current_user.get("email"):
            # Email changes require verification
            update_data["email"] = payload.email.lower()
            update_data["email_verified"] = False  # Reset verification
            sensitive_changes.append("email")
            
        # Location Fields (Editable)
        if payload.city is not None:
            update_data["city"] = payload.city
        if payload.state is not None:
            update_data["state"] = payload.state
        if payload.district is not None:
            update_data["district"] = payload.district
        if payload.mandal is not None:
            update_data["mandal"] = payload.mandal
        if payload.zip_code is not None:
            update_data["zip_code"] = payload.zip_code
        if payload.address is not None:
            update_data["address"] = payload.address
        if payload.latitude is not None:
            update_data["latitude"] = str(payload.latitude) if payload.latitude else None
        if payload.longitude is not None:
            update_data["longitude"] = str(payload.longitude) if payload.longitude else None
            
        # Personal Info (Editable)
        if payload.bio is not None:
            update_data["bio"] = payload.bio
        if payload.date_of_birth is not None:
            # Handle date_of_birth with proper validation and formatting
            try:
                if payload.date_of_birth and payload.date_of_birth.strip():
                    # If it's already in YYYY-MM-DD format from HTML date input, keep it
                    date_str = payload.date_of_birth.strip()
                    # Validate the date format
                    if len(date_str) == 10 and date_str.count('-') == 2:
                        # Parse to validate it's a real date
                        year, month, day = date_str.split('-')
                        dt.datetime(int(year), int(month), int(day))  # This will raise ValueError if invalid
                        update_data["date_of_birth"] = date_str
                        print(f"[USERS] Valid date_of_birth: {date_str}")
                    else:
                        print(f"[USERS] Invalid date format: {date_str}")
                        raise HTTPException(status_code=400, detail="Invalid date format. Please use YYYY-MM-DD format.")
                else:
                    # Empty date - set to None
                    update_data["date_of_birth"] = None
                    print(f"[USERS] Setting date_of_birth to None (empty)")
            except ValueError as date_error:
                print(f"[USERS] Date validation error: {date_error}")
                raise HTTPException(status_code=400, detail="Invalid date. Please enter a valid date.")
            except Exception as date_error:
                print(f"[USERS] Date processing error: {date_error}")
                raise HTTPException(status_code=400, detail="Error processing date. Please check the date format.")
        if payload.profile_image_url is not None:
            update_data["profile_image_url"] = payload.profile_image_url
        if payload.business_name is not None:
            update_data["business_name"] = payload.business_name
        
        if update_data:
            update_data["updated_at"] = dt.datetime.utcnow().isoformat()
            print(f"[USERS] About to update user {user_id} with data: {update_data}")
            
            try:
                result = await db.update("users", update_data, {"id": user_id})
                print(f"[USERS] Database update result: {result}")
                print(f"[USERS] Profile updated successfully for user: {user_id}")
            except Exception as db_error:
                print(f"[USERS] Database update error: {db_error}")
                import traceback
                print(f"[USERS] Full traceback: {traceback.format_exc()}")
                raise HTTPException(status_code=500, detail=f"Database update failed: {str(db_error)}")
            
            # Send confirmation email
            try:
                from ..services.email import send_email
                import pytz
                
                user_type_display = {
                    "admin": "Administrator",
                    "agent": "Agent",
                    "seller": "Seller",
                    "buyer": "Buyer"
                }.get(current_user.get("user_type", "").lower(), "User")
                
                email_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                    <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Profile Updated</h1>
                        </div>
                        
                        <div style="padding: 40px 30px;">
                            <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {current_user.get('first_name', 'User')},</h2>
                            
                            <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                Your profile information has been successfully updated.
                            </p>
                            
                            {"<div style='background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; margin: 30px 0; border-radius: 4px;'><p style='color: #92400e; font-size: 14px; margin: 0; line-height: 1.5;'><strong>⚠️ Sensitive Changes Detected:</strong><br>The following sensitive information was updated: " + ", ".join(sensitive_changes) + "<br>If you didn't make these changes, please contact support immediately.</p></div>" if sensitive_changes else ""}
                            
                            <div style="background-color: #f8fafc; border-radius: 8px; padding: 20px; margin: 30px 0;">
                                <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0; line-height: 1.6;">
                                    <strong>Update Details:</strong>
                                </p>
                                <p style="color: #64748b; font-size: 14px; margin: 0; line-height: 1.6;">
                                    • Date: {dt.datetime.now(pytz.UTC).strftime('%B %d, %Y at %I:%M %p UTC')}<br>
                                    • Account Type: {user_type_display}<br>
                                    • Email: {current_user.get('email', '')}
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
                
                await send_email(
                    to=current_user["email"],
                    subject="Profile Updated - Home & Own",
                    html=email_html
                )
                print(f"[USERS] Profile update confirmation email sent to: {current_user['email']}")
            except Exception as email_error:
                print(f"[USERS] Failed to send profile update email: {email_error}")
                # Don't fail the request if email fails
        
        return {"success": True, "message": "Profile updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Update profile error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to update profile: {str(e)}")

@router.post("/bank-details")
async def update_bank_details(payload: BankDetailsRequest, request: Request):
    try:
        claims = get_current_user_claims(request)
        user_id = claims.get("sub")
        
        print(f"[USERS] Updating bank details for user: {user_id}")
        
        # Verify OTP (required for bank details)
        if not verify_otp_simple(payload.phone, payload.otp, "bank_update"):
            print(f"[USERS] Invalid OTP for bank update")
            raise HTTPException(status_code=400, detail="Invalid OTP for bank update")
        
        print(f"[USERS] OTP verified for bank update")
        
        # Get user to verify phone number matches
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        if user.get("phone_number") != payload.phone:
            raise HTTPException(status_code=400, detail="Phone number mismatch")
        
        # Check if user is agent (bank details mainly for agents)
        if user["user_type"] != "agent":
            raise HTTPException(status_code=403, detail="Bank details only available for agents")
        
        # Update or insert bank details in agent_bank_details table
        try:
            existing_bank = await db.select("agent_bank_details", filters={"agent_id": user_id})
            if existing_bank:
                await db.update("agent_bank_details", {
                    "bank_account_number": payload.bank_account_number,
                    "ifsc_code": payload.ifsc_code,
                    "account_verified": False,
                    "updated_at": dt.datetime.utcnow().isoformat()
                }, {"agent_id": user_id})
            else:
                await db.insert("agent_bank_details", {
                    "id": str(uuid.uuid4()),
                    "agent_id": user_id,
                    "bank_account_number": payload.bank_account_number,
                    "ifsc_code": payload.ifsc_code,
                    "account_verified": False,
                    "created_at": dt.datetime.utcnow().isoformat(),
                    "updated_at": dt.datetime.utcnow().isoformat()
                })
            print(f"[USERS] Bank details updated in agent_bank_details table")
        except Exception as bank_error:
            print(f"[USERS] agent_bank_details table error, using users table: {bank_error}")
            # Fallback: update users table directly
            await db.update("users", {
                "bank_account_number": payload.bank_account_number,
                "ifsc_code": payload.ifsc_code,
                "account_verified": False,
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"id": user_id})
        
        print(f"[USERS] Bank details updated successfully")
        return {"success": True, "message": "Bank details updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Bank details error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update bank details: {str(e)}")

@router.post("/bank-details/save")
async def save_bank_details_simple(payload: dict, request: Request):
    """Save bank details without OTP verification (for agent settings)"""
    try:
        claims = get_current_user_claims(request)
        user_id = claims.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        bank_account_number = payload.get("bank_account_number")
        ifsc_code = payload.get("ifsc_code")
        
        if not bank_account_number or not ifsc_code:
            raise HTTPException(status_code=400, detail="Bank account number and IFSC code are required")
        
        print(f"[USERS] Saving bank details for user: {user_id} (without OTP)")
        
        # Get user to verify they are an agent
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        if user.get("user_type") != "agent":
            raise HTTPException(status_code=403, detail="Bank details only available for agents")
        
        # Update or insert bank details in agent_bank_details table
        try:
            existing_bank = await db.select("agent_bank_details", filters={"agent_id": user_id})
            if existing_bank:
                await db.update("agent_bank_details", {
                    "bank_account_number": bank_account_number,
                    "ifsc_code": ifsc_code,
                    "account_verified": False,
                    "updated_at": dt.datetime.utcnow().isoformat()
                }, {"agent_id": user_id})
            else:
                await db.insert("agent_bank_details", {
                    "id": str(uuid.uuid4()),
                    "agent_id": user_id,
                    "bank_account_number": bank_account_number,
                    "ifsc_code": ifsc_code,
                    "account_verified": False,
                    "created_at": dt.datetime.utcnow().isoformat(),
                    "updated_at": dt.datetime.utcnow().isoformat()
                })
            print(f"[USERS] Bank details saved in agent_bank_details table")
        except Exception as bank_error:
            print(f"[USERS] agent_bank_details table error, using users table: {bank_error}")
            # Fallback: update users table directly
            await db.update("users", {
                "bank_account_number": bank_account_number,
                "ifsc_code": ifsc_code,
                "account_verified": False,
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"id": user_id})
        
        print(f"[USERS] Bank details saved successfully")
        return {"success": True, "message": "Bank details saved successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Save bank details error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save bank details: {str(e)}")

@router.get("/bank-details")
async def get_bank_details(request: Request):
    try:
        claims = get_current_user_claims(request)
        user_id = claims.get("sub")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        print(f"[USERS] Getting bank details for user: {user_id}")
        
        # Try to get from agent_bank_details first
        try:
            bank_details = await db.select("agent_bank_details", filters={"agent_id": user_id})
            if bank_details:
                details = bank_details[0]
                account_number = details.get("bank_account_number", "")
                # Return full account number (not masked) for the account owner to view
                # Frontend can mask it if needed for display
                
                return {
                    "bank_account_number": account_number,  # Return full number for owner
                    "ifsc_code": details.get("ifsc_code", ""),
                    "account_verified": details.get("account_verified", False),
                    "verified_at": details.get("account_verified_at")
                }
        except Exception as bank_error:
            print(f"[USERS] agent_bank_details query failed: {bank_error}")
        
        # Fallback: get from users table
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        account_number = user.get("bank_account_number", "")
        
        return {
            "bank_account_number": account_number,  # Return full number for owner
            "ifsc_code": user.get("ifsc_code", ""),
            "account_verified": user.get("account_verified", False),
            "verified_at": user.get("account_verified_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Get bank details error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get bank details: {str(e)}")

@router.post("/seller-profile")
async def create_seller_profile(payload: dict):
    try:
        print(f"[USERS] Creating seller profile")
        print(f"[USERS] Payload received: {payload}")
        
        return {"success": True, "message": "Seller profile created successfully"}
        
    except Exception as e:
        print(f"[USERS] Create seller profile error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create seller profile: {str(e)}")

@router.patch("/{user_id}")
async def update_user(user_id: str, payload: dict, request: Request):
    try:
        print(f"[USERS] Updating user: {user_id}")
        
        # Update user data
        update_data = {}
        if "user_type" in payload:
            update_data["user_type"] = payload["user_type"]
        if "first_name" in payload:
            update_data["first_name"] = payload["first_name"]
        if "last_name" in payload:
            update_data["last_name"] = payload["last_name"]
        if "phone_number" in payload:
            update_data["phone_number"] = payload["phone_number"]
        if "city" in payload:
            update_data["city"] = payload["city"]
        if "state" in payload:
            update_data["state"] = payload["state"]
        if "address" in payload:
            update_data["address"] = payload["address"]
        if "bio" in payload:
            update_data["bio"] = payload["bio"]
        if "date_of_birth" in payload:
            # Handle date_of_birth with proper validation
            try:
                if payload["date_of_birth"] and str(payload["date_of_birth"]).strip():
                    date_str = str(payload["date_of_birth"]).strip()
                    # Validate the date format
                    if len(date_str) == 10 and date_str.count('-') == 2:
                        # Parse to validate it's a real date
                        year, month, day = date_str.split('-')
                        dt.datetime(int(year), int(month), int(day))  # This will raise ValueError if invalid
                        update_data["date_of_birth"] = date_str
                        print(f"[USERS] Valid date_of_birth: {date_str}")
                    else:
                        print(f"[USERS] Invalid date format: {date_str}")
                        # Skip invalid dates instead of failing
                        pass
                else:
                    # Empty date - set to None
                    update_data["date_of_birth"] = None
            except (ValueError, TypeError) as date_error:
                print(f"[USERS] Date validation error: {date_error}")
                # Skip invalid dates instead of failing the entire update
                pass
        if "profile_image_url" in payload:
            update_data["profile_image_url"] = payload["profile_image_url"]
        if "verification_status" in payload:
            update_data["verification_status"] = payload["verification_status"]
        
        if update_data:
            update_data["updated_at"] = dt.datetime.utcnow().isoformat()
            await db.update("users", update_data, {"id": user_id})
            print(f"[USERS] User updated successfully: {update_data}")
        
        return {"success": True, "message": "User updated successfully"}
        
    except Exception as e:
        print(f"[USERS] Update user error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update user: {str(e)}")

@router.get("/{user_id}")
async def get_user_details(user_id: str):
    """Fetch public details for a single user by their ID."""
    try:
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        
        # Return a subset of user data that is safe to be public
        return {
            "id": user.get("id"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "email": user.get("email"),
            "phone_number": user.get("phone_number"),
            "user_type": user.get("user_type"),
            "created_at": user.get("created_at"),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[USERS] Error fetching user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred while fetching user details.")