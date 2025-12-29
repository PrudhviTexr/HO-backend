"""
SMS Service for sending OTP via Twilio
"""
import os
from typing import Dict, Any
from ..core.config import settings

async def send_sms_otp(phone: str, otp: str, action: str = "verification") -> Dict[str, Any]:
    """
    Send OTP via SMS using Twilio
    
    Args:
        phone: Phone number to send OTP to
        otp: The OTP code to send
        action: The action type (verification, password_reset, etc.)
    
    Returns:
        Dict with success status and message
    """
    try:
        # Check if Twilio credentials are available
        account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', None)
        auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', None)
        from_number = getattr(settings, 'TWILIO_PHONE_NUMBER', None)
        
        if not all([account_sid, auth_token, from_number]):
            print(f"[SMS] Twilio credentials not configured - development mode")
            return {
                "success": True,
                "message": f"OTP {otp} would be sent to {phone} (dev mode)",
                "dev_mode": True
            }
        
        # Try to send SMS via Twilio
        try:
            from twilio.rest import Client
            
            client = Client(account_sid, auth_token)
            
            # Format message based on action
            if action == "verification":
                message_body = f"Your Home & Own verification code is: {otp}. Valid for 10 minutes."
            elif action == "password_reset":
                message_body = f"Your Home & Own password reset code is: {otp}. Valid for 10 minutes."
            else:
                message_body = f"Your Home & Own code is: {otp}. Valid for 10 minutes."
            
            # Send SMS
            message = client.messages.create(
                body=message_body,
                from_=from_number,
                to=phone
            )
            
            print(f"[SMS] OTP sent successfully to {phone}, SID: {message.sid}")
            return {
                "success": True,
                "message": "OTP sent successfully",
                "sid": message.sid
            }
            
        except ImportError:
            print(f"[SMS] Twilio package not installed - development fallback")
            return {
                "success": True,
                "message": f"OTP {otp} would be sent to {phone} (twilio not installed)",
                "dev_mode": True
            }
        except Exception as twilio_error:
            print(f"[SMS] Twilio error: {twilio_error}")
            return {
                "success": False,
                "error": f"Failed to send SMS: {str(twilio_error)}"
            }
            
    except Exception as e:
        print(f"[SMS] SMS service error: {e}")
        return {
            "success": False,
            "error": f"SMS service error: {str(e)}"
        }

def format_phone_number(phone: str) -> str:
    """
    Format phone number for Twilio (E.164 format)
    
    Args:
        phone: Raw phone number
        
    Returns:
        Formatted phone number
    """
    # Remove all non-digit characters
    digits_only = ''.join(filter(str.isdigit, phone))
    
    # Add country code if not present
    if len(digits_only) == 10:
        # Assume US number if 10 digits
        return f"+1{digits_only}"
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        # US number with country code
        return f"+{digits_only}"
    elif len(digits_only) >= 10:
        # International number
        return f"+{digits_only}"
    else:
        # Invalid number
        return phone
