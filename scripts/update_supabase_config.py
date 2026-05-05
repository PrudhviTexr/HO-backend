#!/usr/bin/env python3
"""
Update Supabase Configuration Script
Updates all configuration files with new Supabase credentials
"""

import re
from pathlib import Path

# New Supabase credentials
NEW_SUPABASE_URL = "https://ajymffxpunxoqcmunohx.supabase.co"
NEW_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqeW1mZnhwdW54b3FjbXVub2h4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTYzNjY4OCwiZXhwIjoyMDY3MjEyNjg4fQ.OhWOjkmDxOeX5WgefvTTLOMZPRd3zjkEPAJyqcisfXM"

# Old Supabase URL (for finding and replacing)
OLD_SUPABASE_URL = "https://ajymffxpunxoqcmunohx.supabase.co"

# Files to update
FILES_TO_UPDATE = [
    {
        "path": "python_api/app/db/supabase_client.py",
        "patterns": [
            (r'SUPABASE_URL = "https://ajymffxpunxoqcmunohx\.supabase\.co"', f'SUPABASE_URL = "{NEW_SUPABASE_URL}"'),
            (r'SUPABASE_KEY = ".*"', f'SUPABASE_KEY = "{NEW_ANON_KEY}"  # TODO: Replace with SERVICE_ROLE_KEY'),
        ]
    },
    {
        "path": "python_api/app/core/config.py",
        "patterns": [
            (r'SUPABASE_URL: str = os\.getenv\("SUPABASE_URL", "https://ajymffxpunxoqcmunohx\.supabase\.co"\)', 
             f'SUPABASE_URL: str = os.getenv("SUPABASE_URL", "{NEW_SUPABASE_URL}")'),
        ]
    },
    {
        "path": "python_api/app/services/supabase_storage.py",
        "patterns": [
            (r'SUPABASE_URL = os\.environ\.get\(\'SUPABASE_URL\'\)', 
             f'SUPABASE_URL = os.environ.get(\'SUPABASE_URL\', \'{NEW_SUPABASE_URL}\')'),
        ]
    },
]


def update_file(file_path: Path, patterns: list):
    """Update a file with new patterns"""
    if not file_path.exists():
        print(f"[WARN] File not found: {file_path}")
        return False
    
    try:
        content = file_path.read_text(encoding='utf-8')
        original_content = content
        
        for pattern, replacement in patterns:
            content = re.sub(pattern, replacement, content)
        
        if content != original_content:
            file_path.write_text(content, encoding='utf-8')
            print(f"[OK] Updated: {file_path}")
            return True
        else:
            print(f"[INFO] No changes needed: {file_path}")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error updating {file_path}: {str(e)}")
        return False


def main():
    """Main entry point"""
    print("=" * 80)
    print("Updating Supabase Configuration")
    print("=" * 80)
    print(f"New Supabase URL: {NEW_SUPABASE_URL}")
    print("=" * 80)
    
    base_path = Path(__file__).parent.parent.parent
    updated_count = 0
    
    for file_config in FILES_TO_UPDATE:
        file_path = base_path / file_config["path"]
        if update_file(file_path, file_config["patterns"]):
            updated_count += 1
    
    print("\n" + "=" * 80)
    print(f"Updated {updated_count} file(s)")
    print("=" * 80)
    
    print("\n[IMPORTANT] NEXT STEPS:")
    print("1. Update .env files with new Supabase credentials:")
    print(f"   SUPABASE_URL={NEW_SUPABASE_URL}")
    print(f"   SUPABASE_ANON_KEY={NEW_ANON_KEY}")
    print("   SUPABASE_SERVICE_ROLE_KEY=<get from Supabase dashboard>")
    print("\n2. For frontend, create/update .env file with:")
    print(f"   VITE_SUPABASE_URL={NEW_SUPABASE_URL}")
    print(f"   VITE_SUPABASE_ANON_KEY={NEW_ANON_KEY}")
    print("\n3. Get SERVICE_ROLE_KEY from:")
    print(f"   https://{NEW_SUPABASE_URL.replace('https://', '').split('/')[0]}/project/default/settings/api")
    print("\n4. Update python_api/app/db/supabase_client.py with SERVICE_ROLE_KEY")
    print("   (not anon key - service role key is needed for backend operations)")


if __name__ == "__main__":
    main()

