import os
import random
import datetime as dt
from typing import Optional, Dict, Any
from ..core.config import settings

# In-memory OTP storage for development (use Redis in production)
_otp_storage: Dict[str, Any] = {}

# In-memory temporary signup storage (save to DB only after OTP verification)
_temp_signup_storage: Dict[str, Any] = {}

def _gen_code(length: int = 6) -> str:
    """Generate random OTP code"""
    return ''.join(str(random.randint(0, 9)) for _ in range(length))

async def send_otp_simple(phone: str, action: str = "verification", code: Optional[str] = None) -> str:
    """Create an OTP and send via Twilio if configured. Async so callers can await email backup."""
    
    token = code or _gen_code()
    now = dt.datetime.utcnow()
    expires = now + dt.timedelta(minutes=settings.OTP_EXP_MIN)
    
    print(f"[OTP] Generating OTP for {phone}, action: {action}")
    
    # Store OTP in memory for development
    otp_key = f"{phone}:{action}"
    _otp_storage[otp_key] = {
        "token": token,
        "expires_at": expires,
        "used": False,
        "created_at": now
    }
    
    print(f"[OTP] Created OTP: {token} (expires: {expires.strftime('%H:%M:%S')})")

    # Send via Twilio if configured
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_FROM_NUMBER:
        try:
            from twilio.rest import Client
            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
            
            # Create action-specific message
            action_messages = {
                "verification": f"Your Home & Own verification code is: {token}. Valid for {settings.OTP_EXP_MIN} minutes.",
                "bank_update": f"Your OTP for bank details update: {token}. Valid for {settings.OTP_EXP_MIN} minutes.",
                "password_change": f"Your OTP for password change: {token}. Valid for {settings.OTP_EXP_MIN} minutes.",
                "password_reset": f"Your OTP for password reset: {token}. Valid for {settings.OTP_EXP_MIN} minutes.",
                "profile_update": f"Your OTP for profile update: {token}. Valid for {settings.OTP_EXP_MIN} minutes.",
                "sensitive_action": f"Your Home & Own security code: {token}. Valid for {settings.OTP_EXP_MIN} minutes."
            }
            
            message_body = action_messages.get(action, f"Your Home & Own verification code is: {token}")
            
            message = client.messages.create(
                body=message_body,
                from_=settings.TWILIO_FROM_NUMBER,
                to=phone
            )
            print(f"[OTP] SMS sent via Twilio to {phone}, SID: {message.sid}")
        except Exception as sms_error:
            print(f"[OTP] Twilio SMS failed: {sms_error}")
            # Continue without failing - OTP is still created for development
    else:
        print(f"[OTP] Development mode: OTP {token} for {phone} (action: {action})")
        print(f"[OTP] Add to Twilio credentials to enable SMS")
        # Also send OTP via email as backup (async)
        try:
            from ..services.email import send_otp_email
            await send_otp_email(phone.replace('+91', '') + '@example.com', token, action)
            print(f"[OTP] OTP also sent via email backup")
        except Exception as email_error:
            print(f"[OTP] Email backup failed: {email_error}")

    return token

def verify_phone_otp(phone: str, token: str, action: str = "verification") -> bool:
    """Verify phone OTP - alias for verify_otp_simple"""
    return verify_otp_simple(phone, token, action)

def verify_otp_simple(phone: str, token: str, action: str = "verification") -> bool:
    """Verify OTP and mark as used"""
    now = dt.datetime.utcnow()
    
    print(f"[OTP] Verifying OTP: {token} for {phone}, action: {action}")
    
    # Find valid OTP
    otp_key = f"{phone}:{action}"
    otp_record = _otp_storage.get(otp_key)
    
    if not otp_record:
        print(f"[OTP] No OTP found for {phone}:{action}")
        return False
    
    if otp_record["used"]:
        print(f"[OTP] OTP already used for {phone}:{action}")
        return False
    
    if otp_record["expires_at"] < now:
        print(f"[OTP] OTP expired for {phone}:{action}")
        return False
    
    if otp_record["token"] != token:
        print(f"[OTP] Invalid OTP: {token} for {phone}")
        return False
    
    # Mark as used
    otp_record["used"] = True
    
    print(f"[OTP] OTP verified successfully for {phone}")
    return True

def cleanup_expired_otps():
    """Clean up expired OTP tokens"""
    now = dt.datetime.utcnow()
    expired_keys = []
    
    for key, otp_data in _otp_storage.items():
        if otp_data["expires_at"] < now:
            expired_keys.append(key)
    
    for key in expired_keys:
        del _otp_storage[key]
    
    if expired_keys:
        print(f"[OTP] Cleaned up {len(expired_keys)} expired OTPs")

def get_otp_status(phone: str, action: str = "verification") -> dict:
    """Get OTP status for debugging"""
    otp_key = f"{phone}:{action}"
    otp_record = _otp_storage.get(otp_key)
    
    if not otp_record:
        return {"exists": False}
    
    return {
        "exists": True,
        "token": otp_record["token"],
        "expires_at": otp_record["expires_at"].isoformat(),
        "used": otp_record["used"],
        "expired": otp_record["expires_at"] < dt.datetime.utcnow()
    }

# Email OTP functions
async def send_email_otp(email: str, action: str = "email_verification", code: Optional[str] = None) -> str:
    """Create an email OTP and send via email"""
    
    token = code or _gen_code()
    now = dt.datetime.utcnow()
    expires = now + dt.timedelta(minutes=settings.OTP_EXP_MIN)
    
    print(f"[EMAIL-OTP] Generating email OTP for {email}, action: {action}")
    
    # Store OTP in memory for development
    otp_key = f"email:{email}:{action}"
    _otp_storage[otp_key] = {
        "token": token,
        "expires_at": expires,
        "used": False,
        "created_at": now
    }
    
    print(f"[EMAIL-OTP] Created email OTP: {token} (expires: {expires.strftime('%H:%M:%S')})")

    # Send via email
    try:
        from ..services.email import send_otp_email
        await send_otp_email(email, token, action)
        print(f"[EMAIL-OTP] Email OTP sent to {email}")
    except Exception as email_error:
        print(f"[EMAIL-OTP] Email OTP send failed: {email_error}")
        # Continue without failing - OTP is still created

    return token

def verify_email_otp(email: str, token: str, action: str = "email_verification") -> bool:
    """Verify email OTP and mark as used"""
    now = dt.datetime.utcnow()
    
    print(f"[EMAIL-OTP] Verifying email OTP: {token} for {email}, action: {action}")
    
    # Find valid OTP
    otp_key = f"email:{email}:{action}"
    otp_record = _otp_storage.get(otp_key)
    
    if not otp_record:
        print(f"[EMAIL-OTP] No email OTP found for {email}:{action}")
        return False
    
    if otp_record["used"]:
        print(f"[EMAIL-OTP] Email OTP already used for {email}:{action}")
        return False
    
    if otp_record["expires_at"] < now:
        print(f"[EMAIL-OTP] Email OTP expired for {email}:{action}")
        return False
    
    if otp_record["token"] != token:
        print(f"[EMAIL-OTP] Invalid email OTP: {token} for {email}")
        return False
    
    # Mark as used
    otp_record["used"] = True
    
    print(f"[EMAIL-OTP] Email OTP verified successfully for {email}")
    return True

# Temporary signup storage functions
def store_temp_signup(user_id: str, signup_data: Dict[str, Any]):
    """Store signup data temporarily (until OTP verification)"""
    _temp_signup_storage[user_id] = signup_data
    print(f"[TEMP-SIGNUP] Stored temporary signup data for user {user_id}")

def get_temp_signup(user_id: str) -> Optional[Dict[str, Any]]:
    """Get temporary signup data"""
    return _temp_signup_storage.get(user_id)

def delete_temp_signup(user_id: str):
    """Delete temporary signup data after successful DB save"""
    if user_id in _temp_signup_storage:
        del _temp_signup_storage[user_id]
        print(f"[TEMP-SIGNUP] Deleted temporary signup data for user {user_id}")

def get_email_otp_status(email: str, action: str = "email_verification") -> dict:
    """Get email OTP status for debugging"""
    otp_key = f"email:{email}:{action}"
    otp_record = _otp_storage.get(otp_key)
    
    if not otp_record:
        return {"exists": False}
    
    return {
        "exists": True,
        "token": otp_record["token"],
        "expires_at": otp_record["expires_at"].isoformat(),
        "used": otp_record["used"],
        "expired": otp_record["expires_at"] < dt.datetime.utcnow()
    }