from __future__ import annotations
import secrets
from passlib.context import CryptContext
import os, datetime as dt
import jwt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Hash password using bcrypt"""
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    # Bcrypt has a 72-byte limit for passwords. Truncate if necessary.
    # Use bcrypt directly to avoid passlib's internal encoding issues
    import bcrypt
    
    try:
        # Convert password to bytes to check actual byte length
        password_bytes = password.encode('utf-8')
        
        # Log before truncation
        password_bytes_len_before = len(password_bytes)
        
        # If password exceeds 72 bytes, truncate at byte level
        if len(password_bytes) > 72:
            # Truncate to exactly 72 bytes
            password_bytes = password_bytes[:72]
            print(f"[CRYPTO] Password truncated from {password_bytes_len_before} to {len(password_bytes)} bytes")
        
        # Use bcrypt directly instead of passlib to avoid encoding issues
        # bcrypt.checkpw expects bytes for both password and hash
        password_hash_bytes = password_hash.encode('utf-8')
        
        # Verify using bcrypt directly
        result = bcrypt.checkpw(password_bytes, password_hash_bytes)
        return result
        
    except ValueError as e:
        # If we still get a ValueError about password length, log detailed info
        password_bytes_len = len(password.encode('utf-8')) if password else 0
        password_hash_len = len(password_hash.encode('utf-8')) if password_hash else 0
        print(f"[CRYPTO] Password verification ValueError: {e}")
        print(f"[CRYPTO] Password string length: {len(password) if password else 0}")
        print(f"[CRYPTO] Password bytes length: {password_bytes_len}")
        print(f"[CRYPTO] Password hash string length: {len(password_hash) if password_hash else 0}")
        print(f"[CRYPTO] Password hash bytes length: {password_hash_len}")
        # Re-raise the error
        raise
    except Exception as e:
        # Log any other errors
        print(f"[CRYPTO] Password verification error: {e}")
        print(f"[CRYPTO] Error type: {type(e).__name__}")
        # Fall back to passlib if bcrypt fails
        try:
            return pwd_context.verify(password, password_hash)
        except Exception as fallback_error:
            print(f"[CRYPTO] Fallback to passlib also failed: {fallback_error}")
            raise

def generate_token() -> str:
    """Generate secure random token"""
    return secrets.token_urlsafe(32)

ALGO = "HS256"

def issue_user_token(user_id: str, user_type: str) -> str:
    """Issue JWT token for user"""
    secret = os.getenv("JWT_SECRET", "devsecret")
    # Read expiration hours from env (fallback to 24)
    exp_hours_env = os.getenv("JWT_EXPIRATION_HOURS")
    try:
        exp_hours = int(exp_hours_env) if exp_hours_env is not None else 24
        if exp_hours <= 0:
            raise ValueError("non-positive")
    except Exception:
        exp_hours = 24

    now = dt.datetime.utcnow()
    # Use integer UNIX timestamps for exp and iat to be compatible with all PyJWT versions
    exp_ts = int((now + dt.timedelta(hours=exp_hours)).timestamp())
    iat_ts = int(now.timestamp())
    payload = {
        "sub": str(user_id),
        "role": user_type,
        "exp": exp_ts,
        "iat": iat_ts,
    }
    try:
        token = jwt.encode(payload, secret, algorithm=ALGO)
    except Exception as e:
        # Log detailed debug info to make production issues diagnosable
        try:
            print(f"[JWT] Encode error: {e}")
            print(f"[JWT] Payload: {payload}")
            print(f"[JWT] Secret available: {'yes' if secret else 'no'}, len(secret)={len(secret) if secret else 0}")
        except Exception:
            pass
        raise

    # PyJWT may return bytes on some versions; ensure we return a str
    if isinstance(token, bytes):
        return token.decode('utf-8')
    return token

def verify_user_token(token: str) -> dict | None:
    """Verify JWT token and return claims"""
    secret = os.getenv("JWT_SECRET", "devsecret")
    try:
        data = jwt.decode(token, secret, algorithms=[ALGO])
        return data
    except jwt.ExpiredSignatureError:
        print("[JWT] Token expired")
        return None
    except jwt.InvalidTokenError as e:
        print(f"[JWT] Invalid token: {e}")
        return None
    except Exception as e:
        print(f"[JWT] Token verification error: {e}")
        return None


def generate_refresh_token(length: int = 48) -> str:
    """Generate a secure refresh token string"""
    return secrets.token_urlsafe(length)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage using bcrypt directly"""
    import bcrypt
    # Convert token to bytes and truncate if necessary (bcrypt has 72-byte limit)
    token_bytes = token.encode('utf-8')
    if len(token_bytes) > 72:
        token_bytes = token_bytes[:72]
    # Generate salt and hash using bcrypt directly
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(token_bytes, salt)
    # Return as string
    return hashed.decode('utf-8') if isinstance(hashed, bytes) else hashed


def verify_refresh_token_hash(token: str, token_hash: str) -> bool:
    """Verify a refresh token against its stored hash"""
    try:
        import bcrypt
        # Convert token to bytes and truncate if necessary (bcrypt has 72-byte limit)
        token_bytes = token.encode('utf-8')
        if len(token_bytes) > 72:
            token_bytes = token_bytes[:72]
        # Convert hash to bytes
        token_hash_bytes = token_hash.encode('utf-8')
        # Verify using bcrypt directly
        return bcrypt.checkpw(token_bytes, token_hash_bytes)
    except Exception:
        return False