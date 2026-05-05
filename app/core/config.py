import os
from pathlib import Path

# Try to load environment variables from a local .env (python_api/.env)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / '.env'
    # Load and prefer explicit file if present
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[CONFIG] Loaded environment from: {env_path}")
    else:
        # fall back to any .env in cwd
        load_dotenv()
        print(f"[CONFIG] No explicit .env at {env_path}; loaded default .env if present")
except Exception:
    # If python-dotenv isn't available, continue using OS environment variables
    print("[CONFIG] python-dotenv not available or failed to load; using OS environment variables")

class Settings:
    # Supabase Configuration (Database Only)
    # All environment variables are required - no defaults for production
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    # Read SERVICE_ROLE_KEY directly from file if dotenv truncates it
    _service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not _service_role_key or len(_service_role_key) < 200:
        # dotenv might have truncated, read directly from .env file
        try:
            env_path = Path(__file__).resolve().parent.parent / '.env'
            if env_path.exists():
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('SUPABASE_SERVICE_ROLE_KEY='):
                            _service_role_key = line.split('=', 1)[1].strip().strip('"').strip("'")
                            break
        except Exception as e:
            pass
    SUPABASE_SERVICE_ROLE_KEY: str = _service_role_key
    
    # SMTP Configuration
    GMAIL_USERNAME: str = os.getenv("GMAIL_USERNAME", "")
    GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
    
    # Site Configuration
    SITE_URL: str = os.getenv("SITE_URL", "https://homeandown.com")
    CORS_ORIGIN: str = os.getenv("CORS_ORIGIN", "https://homeandown.com,https://www.homeandown.com")
    # Mobile/WebView origins (Capacitor, Ionic, null). Comma-separated; add custom app schemes here.
    CORS_ORIGIN_MOBILE: str = os.getenv("CORS_ORIGIN_MOBILE", "capacitor://localhost,ionic://localhost,null")
    PYTHON_API_KEY: str = os.getenv("PYTHON_API_KEY", "")
    
    # Twilio Configuration for OTP
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")
    
    # OTP Configuration
    OTP_EXP_MIN: int = int(os.getenv("OTP_EXP_MIN", "5"))
    
    # JWT Configuration
    # JWT_SECRET must be set in environment variables for production
    JWT_SECRET: str = os.getenv("JWT_SECRET", "")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # Resend API Key (server-side)
    RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
    RESEND_TEMPLATE_ID: str = os.getenv("RESEND_TEMPLATE_ID", "")
    RESEND_SENDER: str = os.getenv("RESEND_SENDER", "")
    
    # Google Maps API Configuration
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    
    # Support Email Configuration
    SUPPORT_EMAIL: str = os.getenv("SUPPORT_EMAIL", "support@homeandown.com")

# Global settings instance
settings = Settings()

# Debug environment on startup
print(f"[CONFIG] Configuration loaded:")
print(f"[CONFIG]   SUPABASE_URL: {'SET' if settings.SUPABASE_URL else 'MISSING'}")
print(f"[CONFIG]   SERVICE_ROLE_KEY: {'SET' if settings.SUPABASE_SERVICE_ROLE_KEY else 'MISSING'}")
print(f"[CONFIG]   GMAIL_USERNAME: {'SET' if settings.GMAIL_USERNAME else 'MISSING'}")
print(f"[CONFIG]   GMAIL_APP_PASSWORD: {'SET' if settings.GMAIL_APP_PASSWORD else 'MISSING'}")
print(f"[CONFIG]   PYTHON_API_KEY: {'SET' if settings.PYTHON_API_KEY else 'MISSING'}")
print(f"[CONFIG]   GOOGLE_MAPS_API_KEY: {'SET' if settings.GOOGLE_MAPS_API_KEY else 'MISSING'}")