from __future__ import annotations
import os
from typing import Optional, Any

# SQLAlchemy imports are optional in Supabase-only deployments. We import
# them lazily only when a DATABASE_URL / MYSQL_* is present so editor type
# checkers (and environments without SQLAlchemy) don't fail.

# Exported symbols expected elsewhere in the codebase
# Use Any to keep type-checker quiet; these are set at runtime if SQLAlchemy is available
ENGINE: Optional[Any] = None  # type: ignore
SessionLocal: Optional[Any] = None  # type: ignore


def _build_db_url() -> Optional[str]:
    """Build a DB connection URL.

    Prefer a full DATABASE_URL (Postgres/Supabase) or POSTGRES_URL first. For
    backwards compatibility, MYSQL_URL is still supported. If no full URL is
    provided, the code will attempt to compose a MySQL URL from individual
    MYSQL_* env vars.
    """
    # Prefer full database URL when provided (Postgres) or legacy MYSQL_URL.
    # If none is provided we intentionally return None and let the app
    # rely on Supabase client for all DB operations.
    url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or os.getenv("MYSQL_URL")
    if url and url.strip():
        return url.strip()

    # Compose MySQL URL from individual parts as a fallback (legacy).
    host = (os.getenv("MYSQL_HOST") or "127.0.0.1").strip()
    port = (os.getenv("MYSQL_PORT") or "3306").strip()
    db = (os.getenv("MYSQL_DB") or "").strip()
    user = (os.getenv("MYSQL_USER") or "").strip()
    pwd = (os.getenv("MYSQL_PASSWORD") or "").strip()
    if not (db and user):
        # No SQLAlchemy DB configured; return None to indicate Supabase-only mode
        return None
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"


url = _build_db_url()
# Debug log which DB we're using (mask password) and set up ENGINE only when URL present
if not url:
    print("[DB] ℹ️  No SQLAlchemy DATABASE_URL/MYSQL_* configured. Running in Supabase-only mode.")
else:
    # Import SQLAlchemy lazily so missing packages don't break Supabase-only runs
    try:
        from sqlalchemy import create_engine  # type: ignore
        from sqlalchemy.orm import sessionmaker  # type: ignore
    except Exception as e:
        print(f"[DB] ❌ SQLAlchemy not available; skipping SQL engine setup: {e}")
    else:
        # Mask credentials for Postgres (postgres:// or postgresql://)
        try:
            if url.startswith("postgres://") or url.startswith("postgresql://"):
                head, rest = url.split("://", 1)
                creds, tail = rest.split("@", 1)
                if ":" in creds:
                    user, _pwd = creds.split(":", 1)
                    safe = f"{head}://{user}:****@{tail}"
                else:
                    safe = f"{head}://{creds}@{tail}"
                print(f"[DB] Using {safe}")
            elif url.startswith("mysql+pymysql://"):
                head, rest = url.split("://", 1)
                creds, tail = rest.split("@", 1)
                if ":" in creds:
                    user, _pwd = creds.split(":", 1)
                    safe = f"{head}://{user}:****@{tail}"
                else:
                    safe = f"{head}://{creds}@{tail}"
                print(f"[DB] Using {safe}")
            else:
                print(f"[DB] Using {url}")
        except Exception:
            pass

        try:
            engine_kwargs = {"pool_pre_ping": True, "pool_recycle": 3600}
            ENGINE = create_engine(url, **engine_kwargs)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)
        except Exception as e:
            print(f"[DB] ❌ Failed to initialize SQLAlchemy engine: {e}")
            ENGINE = None
            SessionLocal = None
