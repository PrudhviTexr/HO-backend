import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from dotenv import load_dotenv
load_dotenv(APP_ROOT / ".env")

from app.db.database import SessionLocal
from app.db.models import User
from app.core.crypto import hash_password

email = os.getenv("DEFAULT_ADMIN_EMAIL", "admin@homeandown.com").lower()
password = os.getenv("DEFAULT_ADMIN_PASSWORD", "Frisco@2025")

print(f"Seeding admin {email} ...")

db = SessionLocal()
try:
    u = db.query(User).filter(User.email == email).first()
    if u:
        print("Admin already exists; ensuring flags...")
        changed = False
        if u.user_type != "admin":
            u.user_type = "admin"; changed = True
        if not u.email_verified:
            u.email_verified = True; changed = True
        if (u.status or "") != "active":
            u.status = "active"; changed = True
        if (u.verification_status or "") != "approved":
            u.verification_status = "approved"; changed = True
        if changed:
            db.commit()
            print("Admin updated")
        else:
            print("Admin unchanged")
    else:
        u = User(
            email=email,
            password_hash=hash_password(password),
            first_name="Admin",
            last_name="User",
            user_type="admin",
            status="active",
            email_verified=True,
            verification_status="approved",
        )
        db.add(u)
        db.commit()
        print("Admin created")
finally:
    db.close()

print("Done.")
