#!/usr/bin/env python3
"""
Create admin user script
"""
import asyncio
import sys
import os
from pathlib import Path

# Add the app directory to Python path
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

async def create_admin():
    try:
        from app.db.supabase_client import db
        from app.core.crypto import hash_password
        import uuid
        import datetime as dt

        print("🔍 Checking if admin user exists...")

        # Check if admin exists
        try:
            existing = await db.select('users', filters={'email': 'admin@homeandown.com'})
            if existing:
                print('✅ Admin user already exists')
                print('Login credentials:')
                print('Email: admin@homeandown.com')
                print('Password: Frisco@2025')
                return
        except Exception as e:
            print(f"⚠️ Could not check existing users: {e}")

        print("👤 Creating admin user...")

        # Create admin user
        admin_data = {
            'id': str(uuid.uuid4()),
            'email': 'admin@homeandown.com',
            'password_hash': hash_password('Frisco@2025'),
            'first_name': 'Admin',
            'last_name': 'User',
            'user_type': 'admin',
            'status': 'active',
            'email_verified': True,
            'verification_status': 'approved',
            'created_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'updated_at': dt.datetime.now(dt.timezone.utc).isoformat()
        }

        result = await db.insert('users', admin_data)
        print('✅ Admin user created successfully!')
        print('Login credentials:')
        print('Email: admin@homeandown.com')
        print('Password: Frisco@2025')

    except Exception as e:
        print(f'❌ Error creating admin user: {e}')
        import traceback
        print(f'Full error: {traceback.format_exc()}')

if __name__ == "__main__":
    asyncio.run(create_admin())
