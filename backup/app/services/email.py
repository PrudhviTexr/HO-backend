import aiosmtplib
from email.message import EmailMessage
from ..core.config import settings
import datetime
import ssl
import certifi
import os
import requests
import asyncio

async def send_email(to: str, subject: str, html: str, sender: str | None = None):
    """Send email via Gmail SMTP"""
    
    print(f"[EMAIL] Preparing to send email to: {to}")
    print(f"[EMAIL] Subject: {subject}")
    
    msg = EmailMessage()
    
    # Use branded sender
    default_sender = settings.GMAIL_USERNAME
    if default_sender and "<" not in (sender or default_sender):
        branded_sender = f"Home & Own <{default_sender}>"
    else:
        branded_sender = sender or default_sender or "noreply@homeandown.com"
    
    msg["From"] = branded_sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("This email requires HTML support to display properly.")
    msg.add_alternative(html, subtype='html')

    # Check if any email provider is configured
    resend_key = os.getenv("RESEND_API_KEY") or getattr(settings, "RESEND_API_KEY", None)
    emailjs_service = os.getenv("EMAILJS_SERVICE_ID") or getattr(settings, "EMAILJS_SERVICE_ID", None)
    sendgrid_key = os.getenv("SENDGRID_API_KEY") or getattr(settings, "SENDGRID_API_KEY", None)
    has_gmail = settings.GMAIL_USERNAME and settings.GMAIL_APP_PASSWORD
    
    if not resend_key and not emailjs_service and not sendgrid_key and not has_gmail:
        print(f"[EMAIL-ERROR] No email provider configured!")
        print(f"[EMAIL-ERROR] To: {to}")
        print(f"[EMAIL-ERROR] Subject: {subject}")
        print(f"[EMAIL-ERROR] HTML: {html[:200]}...")
        print("[EMAIL-ERROR] Please configure one of: RESEND_API_KEY, EMAILJS_*, SENDGRID_API_KEY, or GMAIL_USERNAME/GMAIL_APP_PASSWORD")
        return {"status": "failed", "error": "No email provider configured"}

    # Clean app password (remove spaces) if Gmail is configured
    app_password = None
    if has_gmail:
        app_password = settings.GMAIL_APP_PASSWORD.replace(" ", "")
        print(f"[EMAIL] Gmail credentials available, will use as fallback if other providers fail")

    # Prefer Resend HTTP API if configured (server-side key keeps secrets safe)
    # (resend_key already checked above)
    resend_template = os.getenv("RESEND_TEMPLATE_ID") or getattr(settings, "RESEND_TEMPLATE_ID", None)
    
    if resend_key:
        # If a template id is configured, use Resend Templates API for consistent branding
        if resend_template:
            print("[EMAIL] Sending via Resend Templates API (RESEND_TEMPLATE_ID detected)")
            try:
                # Attempt to extract verification_link from HTML if present
                verification_link = None
                try:
                    import re
                    m = re.search(r"href=[\'\"]([^\'\"]+)[\'\"]", html)
                    if m:
                        verification_link = m.group(1)
                except Exception:
                    pass

                payload = {
                    "template": resend_template,
                    "to": [to],
                    "from": os.getenv("RESEND_SENDER") or getattr(settings, "RESEND_SENDER", branded_sender),
                    "subject": subject,
                    "data": {
                        "to_name": (to.split('@')[0] if to else ""),
                        "subject": subject,
                        "verification_link": verification_link or "",
                        "html": html,
                    },
                    # include html at top-level to satisfy API validation when template expects it
                    "html": html,
                }
                headers = {
                    "Authorization": f"Bearer {resend_key}",
                    "Content-Type": "application/json",
                }
                loop = asyncio.get_running_loop()
                # Resend templates are sent via the /emails endpoint with a `template` field
                resp = await loop.run_in_executor(None, lambda: requests.post("https://api.resend.com/emails", json=payload, headers=headers, timeout=15))
                if resp.status_code in (200, 201, 202):
                    print(f"[EMAIL] Resend Templates accepted message for delivery: {resp.status_code}")
                    return {"status": "sent", "provider": "resend", "http_status": resp.status_code}
                else:
                    print(f"[EMAIL]  Resend Templates API returned {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"[EMAIL]  Resend Templates send failed: {e}")
            # fallthrough to raw Resend send or other providers
        print("[EMAIL]   Sending via Resend API (RESEND_API_KEY detected)")
        try:
            resend_url = "https://api.resend.com/emails"
            payload = {
                "from": os.getenv("RESEND_SENDER") or getattr(settings, "RESEND_SENDER", branded_sender),
                "to": [to],
                "subject": subject,
                "html": html,
            }
            headers = {
                "Authorization": f"Bearer {resend_key}",
                "Content-Type": "application/json",
            }

            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, lambda: requests.post(resend_url, json=payload, headers=headers, timeout=15))
            if resp.status_code in (200, 201, 202):
                print(f"[EMAIL] Resend accepted message for delivery: {resp.status_code}")
                return {"status": "sent", "provider": "resend", "http_status": resp.status_code}
            else:
                print(f"[EMAIL] Resend API returned {resp.status_code}: {resp.text}")
                print(f"[EMAIL] Response body: {resp.text}")
        except Exception as e:
            print(f"[EMAIL]  Resend send failed: {e}")
        # Fallthrough to EmailJS/SendGrid/SMTP if Resend fails

    # Prefer EmailJS HTTP API if configured (server-side keys keep secrets safe)
    emailjs_service = os.getenv("EMAILJS_SERVICE_ID") or getattr(settings, "EMAILJS_SERVICE_ID", None)
    emailjs_template = os.getenv("EMAILJS_TEMPLATE_ID") or getattr(settings, "EMAILJS_TEMPLATE_ID", None)
    emailjs_user = os.getenv("EMAILJS_USER_ID") or getattr(settings, "EMAILJS_USER_ID", None)
    # Support either EmailJS public user id or a server-side access token
    emailjs_access_token = os.getenv("EMAILJS_ACCESS_TOKEN") or getattr(settings, "EMAILJS_ACCESS_TOKEN", None)
    if emailjs_service and emailjs_template and (emailjs_user or emailjs_access_token):
        print("[EMAIL]   Sending via EmailJS API (EMAILJS_* detected)")
        try:
            # Build payload for EmailJS API
            payload = {
                "service_id": emailjs_service,
                "template_id": emailjs_template,
                # include user_id only if available (client-style public id)
                **({"user_id": emailjs_user} if emailjs_user else {}),
                # include access token in payload for server-side auth if provided
                **({"accessToken": emailjs_access_token} if emailjs_access_token else {}),
                "template_params": {
                    "to_email": to,
                    "to_name": (to.split('@')[0] if to else ""),
                    "subject": subject,
                    "html": html,
                    # verification_link is what your template should use for the CTA
                    "verification_link": None,
                },
            }

            # If caller supplied a verification link inside the html (common in signup flow),
            # attempt to extract it. Otherwise, the signup flow should pass the link via template params.
            # We set it to the API fallback link if present in the HTML.
            try:
                # Look for 'href=' occurrences and grab the first URL as verification_link fallback
                import re
                m = re.search(r"href=[\'\"]([^\'\"]+)[\'\"]", html)
                if m:
                    payload["template_params"]["verification_link"] = m.group(1)
            except Exception:
                pass

            EMAILJS_ENDPOINT = "https://api.emailjs.com/api/v1.0/email/send"

            headers = {"Content-Type": "application/json"}
            # If we have a server-side access token, send it in the Authorization header as well
            if emailjs_access_token:
                headers["Authorization"] = f"Bearer {emailjs_access_token}"

            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, lambda: requests.post(EMAILJS_ENDPOINT, json=payload, headers=headers, timeout=15))
            if resp.status_code in (200, 202):
                print(f"[EMAIL] EmailJS accepted message for delivery: {resp.status_code}")
                return {"status": "sent", "provider": "emailjs", "http_status": resp.status_code}
            else:
                print(f"[EMAIL] EmailJS API returned {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[EMAIL] EmailJS send failed: {e}")
            import traceback
            print(traceback.format_exc())
        # Fallthrough to next provider if EmailJS fails

    # If a SendGrid API key is configured, prefer HTTP API sending to avoid SMTP/TLS problems
    # (sendgrid_key already checked above)
    if sendgrid_key:
        print("[EMAIL]   Sending via SendGrid API (SENDGRID_API_KEY detected)")
        try:
            payload = {
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": settings.GMAIL_USERNAME or "noreply@homeandown.com", "name": "Home & Own"},
                "subject": subject,
                "content": [{"type": "text/html", "value": html}]
            }
            headers = {
                "Authorization": f"Bearer {sendgrid_key}",
                "Content-Type": "application/json"
            }
            resp = requests.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers, timeout=15)
            if resp.status_code in (200, 202):
                print(f"[EMAIL] SendGrid accepted message for delivery: {resp.status_code}")
                return {"status": "sent", "provider": "sendgrid", "http_status": resp.status_code}
            else:
                print(f"[EMAIL] SendGrid API returned {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"[EMAIL] SendGrid send failed: {e}")
            import traceback
            print(traceback.format_exc())
        # Fallthrough to SMTP path if SendGrid fails

    # Try Gmail SMTP as final fallback if configured
    if has_gmail and app_password:
        print("[EMAIL] Attempting Gmail SMTP as final fallback...")
        # Build a TLS context that prefers the OS trust store but can be augmented:
        # - If SMTP_CA_BUNDLE is set, trust that bundle (useful for corporate proxies)
        # - If SMTP_ALLOW_SELF_SIGNED=true is set (dev only), disable verification
        ca_bundle_path = os.getenv("SMTP_CA_BUNDLE")
        allow_insecure = os.getenv("SMTP_ALLOW_SELF_SIGNED", "false").lower() in ("1", "true", "yes")  # Default to false for production security

        if allow_insecure:
            print("[EMAIL] ⚠️ SMTP_ALLOW_SELF_SIGNED is enabled - TLS certificate verification is disabled (development only)")
            tls_ctx = ssl.create_default_context()
            tls_ctx.check_hostname = False
            tls_ctx.verify_mode = ssl.CERT_NONE
        else:
            tls_ctx = ssl.create_default_context()
            # If a custom CA bundle path is provided, try loading it first
            if ca_bundle_path:
                try:
                    tls_ctx.load_verify_locations(cafile=ca_bundle_path)
                    print(f"[EMAIL] Using custom CA bundle from: {ca_bundle_path}")
                except Exception as e:
                    print(f"[EMAIL] ⚠️ Failed to load SMTP_CA_BUNDLE at {ca_bundle_path}: {e}")
            # Also include certifi's bundle to improve compatibility
            try:
                tls_ctx.load_verify_locations(cafile=certifi.where())
            except Exception:
                pass

        try:
            await aiosmtplib.send(
                msg,
                hostname="smtp.gmail.com",
                port=587,
                start_tls=True,
                username=settings.GMAIL_USERNAME,
                password=app_password,
                timeout=30,
                tls_context=tls_ctx,
            )
            print(f"[EMAIL] Email sent successfully via Gmail SMTP to: {to}")
            return {"status": "sent", "provider": "gmail"}
        except Exception as e:
            print(f"[EMAIL] Gmail SMTP failed: {e}")
            import traceback
            print(traceback.format_exc())
    else:
        print(f"[EMAIL] Gmail SMTP not configured, skipping...")
        
    # If we reach here, all email providers failed
    print(f"[EMAIL] ALL EMAIL PROVIDERS FAILED OR NOT CONFIGURED!")
    print(f"[EMAIL-ERROR] Email would have been sent to: {to}")
    print(f"[EMAIL-ERROR] Subject: {subject}")
    print(f"[EMAIL-ERROR] Please configure one of the following:")
    print(f"[EMAIL-ERROR]   - RESEND_API_KEY (recommended)")
    print(f"[EMAIL-ERROR]   - EMAILJS_SERVICE_ID + EMAILJS_TEMPLATE_ID + EMAILJS_USER_ID or EMAILJS_ACCESS_TOKEN")
    print(f"[EMAIL-ERROR]   - SENDGRID_API_KEY")
    print(f"[EMAIL-ERROR]   - GMAIL_USERNAME + GMAIL_APP_PASSWORD")
        
    # Don't raise exception - log and continue (emails shouldn't break the app)
    return {"status": "failed", "error": "All email providers failed or not configured"}

async def send_otp_email(to: str, otp: str, action: str = "verification"):
    """Send OTP via email as backup to SMS"""
    action_messages = {
        "verification": "Email Verification",
        "bank_update": "Bank Details Update",
        "password_change": "Password Change",
        "password_reset": "Password Reset",
        "profile_update": "Profile Update",
        "sensitive_action": "Security Verification"
    }
    
    subject = f"{action_messages.get(action, 'Verification')} Code - Home & Own"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f9fafb; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 12px; padding: 40px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #0ca5e9; margin: 0; font-size: 28px; font-weight: 700;">Home & Own</h1>
                <p style="color: #64748b; margin: 8px 0 0 0;">Security Verification</p>
            </div>
            
            <h2 style="color: #1e293b; margin: 0 0 20px 0; text-align: center;">Your Security Code</h2>
            
            <p style="margin: 0 0 20px 0; font-size: 16px; text-align: center; color: #475569;">
                Your verification code for <strong>{action_messages.get(action, 'verification')}</strong>:
            </p>
            
            <div style="text-align: center; margin: 30px 0;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; display: inline-block; min-width: 200px;">
                    <span style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: white; font-family: monospace;">{otp}</span>
                </div>
            </div>
            
            <div style="background-color: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 16px; margin: 24px 0;">
                <p style="margin: 0; font-size: 14px; color: #92400e; text-align: center;">
                    <strong> This code expires in {settings.OTP_EXP_MIN} minutes</strong>
                </p>
            </div>
            
            <p style="margin: 0 0 24px 0; font-size: 14px; color: #6b7280; text-align: center;">
                If you didn't request this code, please ignore this email or contact support.
            </p>
            
            <div style="text-align: center; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                <p style="font-size: 12px; color: #9ca3af; margin: 0;">
                    Best regards,<br>
                    <strong>The Home & Own Team</strong>
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    await send_email(to, subject, html)
