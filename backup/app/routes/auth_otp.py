from __future__ import annotations
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any

router = APIRouter()


@router.post("/send-otp")
async def send_otp_endpoint(payload: Dict[str, Any] = Body(...)):
    from ..services.otp_service import send_email_otp
    
    # Handle request body
    email = payload.get("email")
    action = payload.get("action", "email_verification")
    
    if not email:
        raise HTTPException(status_code=422, detail="email is required")
    
    print(f"[OTP] Received send OTP request for email: {email}")
    
    # Call the async function
    token = await send_email_otp(email, action)
    
    # Return in format frontend expects
    return {"success": True, "sent": True, "otp": token}


@router.post("/verify-otp")
async def verify_otp_endpoint(payload: Dict[str, Any] = Body(...)):
    from ..services.otp_service import verify_email_otp
    from ..db.supabase_client import db
    import datetime as dt
    
    # Handle request body
    email = payload.get("email")
    otp = payload.get("otp")
    action = payload.get("action", "email_verification")
    
    if not email or not otp:
        raise HTTPException(status_code=422, detail="email and otp are required")
    
    print(f"[OTP] Received verify OTP request for email: {email}")
    
    ok = verify_email_otp(email, otp, action)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    # If OTP verification is successful, update user's email_verified status
    if action == "email_verification":
        try:
            # Find user by email
            users = await db.select("users", filters={"email": email})
            if users:
                user = users[0]
                # Update email_verified to True (boolean) and set email_verified_at
                # Also set verification_status to 'verified' since OTP verification is email verification
                update_data = {
                    "email_verified": True,  # Set as boolean True, not string 'true'
                    "email_verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "verification_status": "verified",  # Set verification_status to verified
                    "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
                }
                # Also ensure status is active if it's pending
                if user.get("status") in ["pending", None, ""]:
                    update_data["status"] = "active"
                await db.update("users", update_data, {"id": user["id"]})
                print(f"[OTP] Updated email_verified=True and verification_status=verified for user: {email}")
        except Exception as update_error:
            print(f"[OTP] Failed to update email_verified status: {update_error}")
            # Don't fail OTP verification if DB update fails - OTP is already verified
    
    # Return in format frontend expects
    return {"success": True}
