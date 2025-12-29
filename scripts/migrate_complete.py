#!/usr/bin/env python3
"""
Complete Supabase Migration Script
Migrates both database tables AND storage buckets from old to new Supabase
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    """Run complete migration: database + storage"""
    print("=" * 80)
    print("COMPLETE SUPABASE MIGRATION")
    print("=" * 80)
    print("This script will migrate:")
    print("  1. All database tables")
    print("  2. All storage buckets, folders, and files")
    print("=" * 80)
    
    response = input("\nDo you want to proceed? (yes/no): ").strip().lower()
    if response != "yes":
        print("[INFO] Migration cancelled.")
        return
    
    # Step 1: Database Migration
    print("\n" + "=" * 80)
    print("STEP 1: DATABASE MIGRATION")
    print("=" * 80)
    
    try:
        from migrate_supabase import SupabaseMigrator
        db_migrator = SupabaseMigrator()
        db_migrator.migrate_all()
    except Exception as e:
        print(f"[ERROR] Database migration failed: {str(e)}")
        response = input("\nContinue with storage migration anyway? (yes/no): ").strip().lower()
        if response != "yes":
            print("[INFO] Migration stopped.")
            return
    
    # Step 2: Storage Migration
    print("\n" + "=" * 80)
    print("STEP 2: STORAGE MIGRATION")
    print("=" * 80)
    
    try:
        from migrate_supabase_storage import StorageMigrator
        storage_migrator = StorageMigrator()
        storage_migrator.migrate_all_storage()
    except Exception as e:
        print(f"[ERROR] Storage migration failed: {str(e)}")
    
    # Final Summary
    print("\n" + "=" * 80)
    print("MIGRATION COMPLETE")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Verify data in new Supabase dashboard")
    print("  2. Test your application with new database")
    print("  3. Update environment variables if not already done")
    print("  4. Update any hardcoded URLs in code")
    print("=" * 80)


if __name__ == "__main__":
    main()

