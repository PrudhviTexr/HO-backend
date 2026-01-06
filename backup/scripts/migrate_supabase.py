#!/usr/bin/env python3
"""
Supabase Database Migration Script
Migrates all data from old Supabase instance to new Supabase instance
"""

import asyncio
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from supabase import create_client, Client
from datetime import datetime

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Old Supabase credentials (from current codebase)
OLD_SUPABASE_URL = "https://ajymffxpunxoqcmunohx.supabase.co"
OLD_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqeW1mZnhwdW54b3FjbXVub2h4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTYzNjY4OCwiZXhwIjoyMDY3MjEyNjg4fQ.OhWOjkmDxOeX5WgefvTTLOMZPRd3zjkEPAJyqcisfXM"

# New Supabase credentials (provided by user)
NEW_SUPABASE_URL = "https://ajymffxpunxoqcmunohx.supabase.co"
NEW_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqeW1mZnhwdW54b3FjbXVub2h4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTYzNjY4OCwiZXhwIjoyMDY3MjEyNjg4fQ.OhWOjkmDxOeX5WgefvTTLOMZPRd3zjkEPAJyqcisfXM"

# NOTE: You'll need to provide the SERVICE_ROLE_KEY for the new Supabase
# Get it from: https://ajymffxpunxoqcmunohx.supabase.co/project/default/settings/api
# For now, we'll use anon key but service role is recommended for migration
# You can set it as an environment variable: export NEW_SUPABASE_SERVICE_KEY="your_key"
import os
NEW_SERVICE_KEY = os.getenv("NEW_SUPABASE_SERVICE_KEY", NEW_ANON_KEY)  # Use service role key if provided

# Table migration order (respecting foreign key dependencies)
TABLE_ORDER = [
    # Location tables (no dependencies)
    "states",
    "districts", 
    "mandals",
    "cities",
    "pincodes",
    
    # User tables
    "users",
    "agent_profiles",
    "seller_profiles",
    "user_approvals",
    
    # Property tables
    "properties",
    
    # Related tables
    "inquiries",
    "bookings",
    "documents",
    "email_verification_tokens",
    "refresh_tokens",
    
    # Assignment and notification tables
    "agent_assignments",
    "notifications",
    
    # Dashboard support tables
    "property_views",
    "saved_properties",
    "system_logs",
    "agent_performance_metrics",
]


class SupabaseMigrator:
    def __init__(self):
        print("=" * 80)
        print("Supabase Database Migration Script")
        print("=" * 80)
        print(f"Old Supabase: {OLD_SUPABASE_URL}")
        print(f"New Supabase: {NEW_SUPABASE_URL}")
        print("=" * 80)
        
        # Initialize clients
        self.old_client: Client = create_client(OLD_SUPABASE_URL, OLD_SERVICE_KEY)
        self.new_client: Client = create_client(NEW_SUPABASE_URL, NEW_SERVICE_KEY)
        
        self.stats = {
            "total_tables": 0,
            "successful": 0,
            "failed": 0,
            "total_records": 0,
            "errors": []
        }
    
    def fetch_all_records(self, client: Client, table: str) -> List[Dict[str, Any]]:
        """Fetch all records from a table with pagination"""
        all_records = []
        page_size = 1000
        offset = 0
        
        while True:
            try:
                response = client.table(table).select("*").range(offset, offset + page_size - 1).execute()
                records = response.data if hasattr(response, 'data') else []
                
                if not records:
                    break
                
                all_records.extend(records)
                offset += page_size
                
                # If we got fewer records than page size, we're done
                if len(records) < page_size:
                    break
                    
            except Exception as e:
                print(f"  ⚠️  Error fetching {table} at offset {offset}: {str(e)}")
                break
        
        return all_records
    
    def insert_records_batch(self, client: Client, table: str, records: List[Dict[str, Any]], batch_size: int = 100) -> int:
        """Insert records in batches"""
        inserted = 0
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            try:
                # Remove any None values that might cause issues
                clean_batch = []
                for record in batch:
                    clean_record = {k: v for k, v in record.items() if v is not None or k in ['id']}
                    clean_batch.append(clean_record)
                
                response = client.table(table).insert(clean_batch).execute()
                inserted += len(batch)
                print(f"    ✓ Inserted batch {i//batch_size + 1} ({len(batch)} records)")
                
            except Exception as e:
                error_msg = f"Error inserting batch {i//batch_size + 1} into {table}: {str(e)}"
                print(f"    ✗ {error_msg}")
                self.stats["errors"].append(error_msg)
                # Try inserting one by one to identify problematic records
                for record in batch:
                    try:
                        clean_record = {k: v for k, v in record.items() if v is not None or k in ['id']}
                        client.table(table).insert(clean_record).execute()
                        inserted += 1
                    except Exception as single_error:
                        print(f"      ✗ Failed to insert record {record.get('id', 'unknown')}: {str(single_error)}")
        
        return inserted
    
    def migrate_table(self, table: str) -> bool:
        """Migrate a single table"""
        print(f"\n📦 Migrating table: {table}")
        
        try:
            # Fetch all records from old database
            print(f"  📥 Fetching records from old database...")
            old_records = self.fetch_all_records(self.old_client, table)
            
            if not old_records:
                print(f"  ℹ️  No records found in {table}")
                return True
            
            print(f"  ✓ Found {len(old_records)} records")
            
            # Check if table exists in new database and has records
            print(f"  📤 Checking new database...")
            new_records = self.fetch_all_records(self.new_client, table)
            
            if new_records:
                print(f"  ⚠️  Table {table} already has {len(new_records)} records in new database")
                response = input(f"  ❓ Do you want to skip this table? (y/n): ").strip().lower()
                if response == 'y':
                    print(f"  ⏭️  Skipping {table}")
                    return True
                else:
                    print(f"  🗑️  Clearing existing records...")
                    # Delete all existing records
                    for record in new_records:
                        try:
                            record_id = record.get('id') or record.get('pincode') or record.get(list(record.keys())[0])
                            if record_id:
                                self.new_client.table(table).delete().eq('id', record_id).execute()
                        except:
                            pass
            
            # Insert records into new database
            print(f"  📤 Inserting {len(old_records)} records into new database...")
            inserted = self.insert_records_batch(self.new_client, table, old_records)
            
            if inserted == len(old_records):
                print(f"  ✅ Successfully migrated {inserted} records")
                self.stats["successful"] += 1
                self.stats["total_records"] += inserted
                return True
            else:
                print(f"  ⚠️  Only {inserted}/{len(old_records)} records migrated")
                self.stats["failed"] += 1
                return False
                
        except Exception as e:
            error_msg = f"Failed to migrate {table}: {str(e)}"
            print(f"  ✗ {error_msg}")
            self.stats["errors"].append(error_msg)
            self.stats["failed"] += 1
            return False
    
    def migrate_all(self):
        """Migrate all tables in the correct order"""
        print("\n🚀 Starting migration process...\n")
        
        self.stats["total_tables"] = len(TABLE_ORDER)
        
        for table in TABLE_ORDER:
            try:
                self.migrate_table(table)
            except KeyboardInterrupt:
                print("\n\n⚠️  Migration interrupted by user")
                break
            except Exception as e:
                print(f"\n✗ Unexpected error migrating {table}: {str(e)}")
                self.stats["errors"].append(f"Unexpected error in {table}: {str(e)}")
        
        # Print summary
        print("\n" + "=" * 80)
        print("MIGRATION SUMMARY")
        print("=" * 80)
        print(f"Total tables: {self.stats['total_tables']}")
        print(f"Successful: {self.stats['successful']}")
        print(f"Failed: {self.stats['failed']}")
        print(f"Total records migrated: {self.stats['total_records']}")
        
        if self.stats["errors"]:
            print(f"\nErrors encountered: {len(self.stats['errors'])}")
            for error in self.stats["errors"]:
                print(f"  - {error}")
        
        print("=" * 80)


def main():
    """Main entry point"""
    print("\n⚠️  IMPORTANT: Make sure you have:")
    print("  1. Run all migrations on the NEW Supabase instance")
    print("  2. Backed up your old database")
    print("  3. Have the SERVICE_ROLE_KEY for the new Supabase (not just anon key)")
    print("\nPress Ctrl+C to cancel, or Enter to continue...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nMigration cancelled.")
        return
    
    migrator = SupabaseMigrator()
    migrator.migrate_all()
    
    print("\n✅ Migration completed!")
    print("\nNext steps:")
    print("  1. Verify data in new Supabase dashboard")
    print("  2. Update .env files with new Supabase credentials")
    print("  3. Test the application with new database")
    print("  4. Migrate storage buckets if needed (manual process)")


if __name__ == "__main__":
    main()

