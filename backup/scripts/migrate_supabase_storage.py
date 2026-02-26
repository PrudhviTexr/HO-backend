#!/usr/bin/env python3
"""
Supabase Storage Migration Script
Migrates all storage buckets, folders, and files from old Supabase to new Supabase
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from supabase import create_client, Client
import requests
from io import BytesIO

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Old Supabase credentials
OLD_SUPABASE_URL = "https://ajymffxpunxoqcmunohx.supabase.co"
OLD_SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqeW1mZnhwdW54b3FjbXVub2h4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTYzNjY4OCwiZXhwIjoyMDY3MjEyNjg4fQ.OhWOjkmDxOeX5WgefvTTLOMZPRd3zjkEPAJyqcisfXM"

# New Supabase credentials
NEW_SUPABASE_URL = "https://ajymffxpunxoqcmunohx.supabase.co"
NEW_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFqeW1mZnhwdW54b3FjbXVub2h4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1MTYzNjY4OCwiZXhwIjoyMDY3MjEyNjg4fQ.OhWOjkmDxOeX5WgefvTTLOMZPRd3zjkEPAJyqcisfXM"

# Get service role key from environment if available
NEW_SERVICE_KEY = os.getenv("NEW_SUPABASE_SERVICE_KEY", NEW_ANON_KEY)


class StorageMigrator:
    def __init__(self):
        print("=" * 80)
        print("Supabase Storage Migration Script")
        print("=" * 80)
        print(f"Old Supabase: {OLD_SUPABASE_URL}")
        print(f"New Supabase: {NEW_SUPABASE_URL}")
        print("=" * 80)
        
        # Initialize clients with service role keys for full access
        self.old_client: Client = create_client(OLD_SUPABASE_URL, OLD_SERVICE_KEY)
        self.new_client: Client = create_client(NEW_SUPABASE_URL, NEW_SERVICE_KEY)
        
        self.stats = {
            "total_buckets": 0,
            "successful_buckets": 0,
            "failed_buckets": 0,
            "total_files": 0,
            "successful_files": 0,
            "failed_files": 0,
            "total_size_mb": 0,
            "errors": []
        }
    
    def list_buckets(self, client: Client) -> List[Dict[str, Any]]:
        """List all buckets in Supabase"""
        try:
            # Use REST API directly since Python client may not support listing buckets
            url = f"{OLD_SUPABASE_URL.rstrip('/')}/storage/v1/bucket"
            headers = {
                "Authorization": f"Bearer {OLD_SERVICE_KEY}",
                "apikey": OLD_SERVICE_KEY
            }
            
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                buckets = response.json()
                return buckets if isinstance(buckets, list) else []
            else:
                print(f"  [WARN] Failed to list buckets via API (status: {response.status_code})")
                # If API fails, return common bucket names
                print(f"  [WARN] Using common bucket names as fallback...")
                return [
                    {"name": "property-images", "public": True},
                    {"name": "profile-images", "public": True},
                    {"name": "documents", "public": False},
                    {"name": "images", "public": True},
                    {"name": "uploads", "public": False},
                ]
        except Exception as e:
            print(f"  [ERROR] Error listing buckets: {str(e)}")
            # Return common bucket names as fallback
            return [
                {"name": "property-images", "public": True},
                {"name": "profile-images", "public": True},
                {"name": "documents", "public": False},
                {"name": "images", "public": True},
                {"name": "uploads", "public": False},
            ]
    
    def list_files_recursive(self, client: Client, bucket: str, folder: str = "", files: List[Dict] = None) -> List[Dict[str, Any]]:
        """Recursively list all files in a bucket, including subfolders"""
        if files is None:
            files = []
        
        try:
            # List files in current folder
            # Supabase storage list returns files and folders
            response = client.storage.from_(bucket).list(folder or None)
            
            if not response:
                return files
            
            for item in response:
                item_name = item.get("name") or item.get("id")
                if not item_name:
                    continue
                
                # Check if it's a folder (folders typically don't have metadata.size)
                is_folder = item.get("metadata") is None or item.get("metadata", {}).get("size") is None
                
                if is_folder and item_name != folder:
                    # It's a folder, recurse into it
                    subfolder = f"{folder}/{item_name}".lstrip("/") if folder else item_name
                    self.list_files_recursive(client, bucket, subfolder, files)
                else:
                    # It's a file
                    file_path = f"{folder}/{item_name}".lstrip("/") if folder else item_name
                    files.append({
                        "name": item_name,
                        "path": file_path,
                        "folder": folder,
                        "size": item.get("metadata", {}).get("size", 0) if item.get("metadata") else 0,
                        "mime_type": item.get("metadata", {}).get("mimetype", "application/octet-stream") if item.get("metadata") else "application/octet-stream",
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                    })
            
            return files
            
        except Exception as e:
            print(f"    [ERROR] Error listing files in {bucket}/{folder}: {str(e)}")
            return files
    
    def download_file(self, client: Client, bucket: str, file_path: str) -> Optional[bytes]:
        """Download a file from old Supabase"""
        try:
            response = client.storage.from_(bucket).download(file_path)
            if response:
                return response
            return None
        except Exception as e:
            print(f"      [ERROR] Failed to download {file_path}: {str(e)}")
            return None
    
    def upload_file(self, client: Client, bucket: str, file_path: str, file_data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Upload a file to new Supabase"""
        try:
            # Create folder structure if needed
            folder_path = "/".join(file_path.split("/")[:-1])
            
            # Upload file
            response = client.storage.from_(bucket).upload(
                file_path,
                file_data,
                file_options={"content-type": content_type, "upsert": True}
            )
            
            if response:
                return True
            return False
        except Exception as e:
            # Check if it's a "bucket not found" error
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                print(f"      [WARN] Bucket {bucket} may not exist in new Supabase. Create it first.")
            else:
                print(f"      [ERROR] Failed to upload {file_path}: {str(e)}")
            return False
    
    def create_bucket(self, client: Client, bucket_name: str, public: bool = False) -> bool:
        """Create a bucket in new Supabase if it doesn't exist"""
        try:
            # Check if bucket exists
            try:
                client.storage.from_(bucket_name).list()
                print(f"    [INFO] Bucket {bucket_name} already exists")
                return True
            except:
                # Bucket doesn't exist, create it
                pass
            
            # Use REST API to create bucket
            url = f"{NEW_SUPABASE_URL.rstrip('/')}/storage/v1/bucket"
            headers = {
                "Authorization": f"Bearer {NEW_SERVICE_KEY}",
                "apikey": NEW_SERVICE_KEY,
                "Content-Type": "application/json"
            }
            
            data = {
                "name": bucket_name,
                "public": public,
                "file_size_limit": None,
                "allowed_mime_types": None
            }
            
            response = requests.post(url, headers=headers, json=data)
            if response.status_code in [200, 201]:
                print(f"    [OK] Created bucket: {bucket_name} (public: {public})")
                return True
            else:
                print(f"    [WARN] Failed to create bucket {bucket_name}: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"    [ERROR] Error creating bucket {bucket_name}: {str(e)}")
            return False
    
    def migrate_bucket(self, bucket_name: str, public: bool = False) -> bool:
        """Migrate a single bucket with all its files and folders"""
        print(f"\n[STORAGE] Migrating bucket: {bucket_name}")
        print(f"  Public: {public}")
        
        try:
            # Create bucket in new Supabase if it doesn't exist
            print(f"  [1/3] Ensuring bucket exists in new Supabase...")
            if not self.create_bucket(self.new_client, bucket_name, public):
                print(f"  [WARN] Could not create bucket {bucket_name}, but continuing...")
            
            # List all files in old bucket
            print(f"  [2/3] Listing all files in old bucket...")
            files = self.list_files_recursive(self.old_client, bucket_name)
            
            if not files:
                print(f"  [INFO] No files found in bucket {bucket_name}")
                return True
            
            print(f"  [INFO] Found {len(files)} files to migrate")
            
            # Migrate each file
            print(f"  [3/3] Migrating {len(files)} files...")
            successful = 0
            failed = 0
            
            for i, file_info in enumerate(files, 1):
                file_path = file_info["path"]
                file_size_mb = file_info.get("size", 0) / (1024 * 1024)
                
                print(f"    [{i}/{len(files)}] {file_path} ({file_size_mb:.2f} MB)", end=" ... ")
                
                # Download from old
                file_data = self.download_file(self.old_client, bucket_name, file_path)
                if not file_data:
                    print("FAILED (download)")
                    failed += 1
                    self.stats["errors"].append(f"Failed to download {bucket_name}/{file_path}")
                    continue
                
                # Upload to new
                content_type = file_info.get("mime_type", "application/octet-stream")
                if self.upload_file(self.new_client, bucket_name, file_path, file_data, content_type):
                    print("OK")
                    successful += 1
                    self.stats["total_files"] += 1
                    self.stats["successful_files"] += 1
                    self.stats["total_size_mb"] += file_size_mb
                else:
                    print("FAILED (upload)")
                    failed += 1
                    self.stats["failed_files"] += 1
                    self.stats["errors"].append(f"Failed to upload {bucket_name}/{file_path}")
            
            print(f"  [SUMMARY] {successful} successful, {failed} failed")
            
            if successful == len(files):
                self.stats["successful_buckets"] += 1
                return True
            elif successful > 0:
                print(f"  [WARN] Partially migrated: {successful}/{len(files)} files")
                self.stats["successful_buckets"] += 1
                return True
            else:
                self.stats["failed_buckets"] += 1
                return False
                
        except Exception as e:
            error_msg = f"Failed to migrate bucket {bucket_name}: {str(e)}"
            print(f"  [ERROR] {error_msg}")
            self.stats["errors"].append(error_msg)
            self.stats["failed_buckets"] += 1
            return False
    
    def migrate_all_storage(self):
        """Migrate all storage buckets"""
        print("\n[START] Starting storage migration process...\n")
        
        # List all buckets in old Supabase
        print("[STEP 1] Listing buckets in old Supabase...")
        buckets = self.list_buckets(self.old_client)
        
        if not buckets:
            print("[ERROR] No buckets found or could not list buckets")
            print("[INFO] You may need to manually specify bucket names")
            return
        
        self.stats["total_buckets"] = len(buckets)
        print(f"[OK] Found {len(buckets)} bucket(s)")
        
        # Migrate each bucket
        for bucket_info in buckets:
            bucket_name = bucket_info.get("name") or bucket_info.get("id")
            public = bucket_info.get("public", False)
            
            if not bucket_name:
                continue
            
            try:
                self.migrate_bucket(bucket_name, public)
            except KeyboardInterrupt:
                print("\n\n[WARN] Migration interrupted by user")
                break
            except Exception as e:
                print(f"\n[ERROR] Unexpected error migrating {bucket_name}: {str(e)}")
                self.stats["errors"].append(f"Unexpected error in {bucket_name}: {str(e)}")
        
        # Print summary
        print("\n" + "=" * 80)
        print("STORAGE MIGRATION SUMMARY")
        print("=" * 80)
        print(f"Total buckets: {self.stats['total_buckets']}")
        print(f"Successful buckets: {self.stats['successful_buckets']}")
        print(f"Failed buckets: {self.stats['failed_buckets']}")
        print(f"Total files migrated: {self.stats['successful_files']}")
        print(f"Failed files: {self.stats['failed_files']}")
        print(f"Total size migrated: {self.stats['total_size_mb']:.2f} MB")
        
        if self.stats["errors"]:
            print(f"\nErrors encountered: {len(self.stats['errors'])}")
            for error in self.stats["errors"][:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(self.stats["errors"]) > 10:
                print(f"  ... and {len(self.stats['errors']) - 10} more errors")
        
        print("=" * 80)


def main():
    """Main entry point"""
    print("\n[IMPORTANT] Make sure you have:")
    print("  1. Created all necessary buckets in the NEW Supabase instance")
    print("  2. Have the SERVICE_ROLE_KEY for the new Supabase (not just anon key)")
    print("  3. Sufficient storage quota in the new Supabase instance")
    print("\nPress Ctrl+C to cancel, or Enter to continue...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n[INFO] Migration cancelled.")
        return
    
    migrator = StorageMigrator()
    migrator.migrate_all_storage()
    
    print("\n[OK] Storage migration completed!")
    print("\nNext steps:")
    print("  1. Verify files in new Supabase Storage dashboard")
    print("  2. Check file permissions (public/private)")
    print("  3. Test file access in your application")
    print("  4. Update any hardcoded storage URLs if needed")


if __name__ == "__main__":
    main()

