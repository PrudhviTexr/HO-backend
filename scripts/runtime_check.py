import os
import sys
from pathlib import Path

print("=== Runtime Check ===")
print(f"Python: {sys.version}")
print(f"Executable: {sys.executable}")
print(f"CWD: {os.getcwd()}")

# Ensure app root on sys.path and .env loaded when run standalone
try:
    APP_ROOT = Path(__file__).resolve().parents[1]
    if str(APP_ROOT) not in sys.path:
        sys.path.insert(0, str(APP_ROOT))
    from dotenv import load_dotenv
    load_dotenv(APP_ROOT / ".env")
except Exception:
    pass

from importlib.metadata import version, PackageNotFoundError

def ver(pkg: str) -> str:
    try:
        return version(pkg)
    except PackageNotFoundError:
        return "not installed"

print("bcrypt:", ver("bcrypt"))
print("passlib:", ver("passlib"))
print("psycopg2:", ver("psycopg2"))
print("SQLAlchemy:", ver("SQLAlchemy"))
print("a2wsgi:", ver("a2wsgi"))

print("\n-- passlib/bcrypt sanity --")
try:
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    h = ctx.hash("test123!")
    ok = ctx.verify("test123!", h)
    print("passlib/bcrypt: OK" if ok else "passlib/bcrypt: VERIFY FAILED")
except Exception as e:
    print("passlib/bcrypt error:", repr(e))

print("\n-- DB connectivity --")
try:
    from sqlalchemy import text
    from app.db.database import ENGINE
    if ENGINE:
        with ENGINE.connect() as conn:
            try:
                r = conn.execute(text("SELECT COUNT(*) FROM users"))
                count = list(r)[0][0]
                print(f"users table count: {count}")
            except Exception as e:
                print("users count query failed:", repr(e))
        print("DB: OK (engine connected)")
    else:
        print("DB: Skipped - running in Supabase-only mode (no SQLAlchemy ENGINE)")
except Exception as e:
    print("DB error:", repr(e))

print("\nEnv summary:")
for k in ("SITE_URL","ROOT_PATH","DATABASE_URL","MYSQL_URL","AUTO_MIGRATE"):
    v = os.getenv(k, "")
    if k in ("DATABASE_URL", "MYSQL_URL") and v:
        try:
            head, rest = v.split("://", 1)
            creds, tail = rest.split("@", 1)
            if ":" in creds:
                user, _pwd = creds.split(":", 1)
                v = f"{head}://{user}:****@{tail}"
        except Exception:
            pass
    print(f"{k} = {v}")

print("=== End ===")
