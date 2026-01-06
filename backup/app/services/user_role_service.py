"""
User Role Management Service
Handles multiple roles per user and role-based access control
"""

import datetime as dt
from typing import List, Dict, Any, Optional
from ..db.supabase_client import db


class UserRoleService:
    """Service for managing user roles and permissions"""
    
    @staticmethod
    async def create_user_role(user_id: str, role: str, status: str = "active", verified: bool = False) -> Dict[str, Any]:
        """Create a new user role"""
        try:
            print(f"[USER_ROLE] Creating role '{role}' for user {user_id}")
            
            role_data = {
                "user_id": user_id,
                "role": role.lower(),
                "status": status,
                "verified": verified,
                "verified_at": dt.datetime.utcnow().isoformat() if verified else None,
                "created_at": dt.datetime.utcnow().isoformat(),
                "updated_at": dt.datetime.utcnow().isoformat()
            }
            
            result = await db.insert("user_roles", role_data)
            print(f"[USER_ROLE] Role '{role}' created successfully for user {user_id}")
            return result
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to create role '{role}' for user {user_id}: {e}")
            raise e
    
    @staticmethod
    async def get_user_roles(user_id: str) -> List[Dict[str, Any]]:
        """Get all roles for a user"""
        try:
            roles = await db.select("user_roles", filters={"user_id": user_id})
            return roles or []
        except Exception as e:
            print(f"[USER_ROLE] Failed to get roles for user {user_id}: {e}")
            return []
    
    @staticmethod
    async def get_active_user_roles(user_id: str) -> List[str]:
        """Get all active and verified roles for a user"""
        try:
            roles = await db.select("user_roles", filters={
                "user_id": user_id,
                "status": "active",
                "verified": True
            })
            return [role.get("role") for role in roles] if roles else []
        except Exception as e:
            print(f"[USER_ROLE] Failed to get active roles for user {user_id}: {e}")
            return []
    
    @staticmethod
    async def has_role(user_id: str, role: str) -> bool:
        """Check if user has a specific active and verified role"""
        try:
            roles = await db.select("user_roles", filters={
                "user_id": user_id,
                "role": role.lower(),
                "status": "active",
                "verified": True
            })
            return len(roles) > 0
        except Exception as e:
            print(f"[USER_ROLE] Failed to check role '{role}' for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def verify_role(user_id: str, role: str) -> bool:
        """Verify a user's role (admin action)"""
        try:
            print(f"[USER_ROLE] Verifying role '{role}' for user {user_id}")
            
            await db.update("user_roles", {
                "verified": True,
                "verified_at": dt.datetime.utcnow().isoformat(),
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {
                "user_id": user_id,
                "role": role.lower()
            })
            
            print(f"[USER_ROLE] Role '{role}' verified successfully for user {user_id}")
            return True
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to verify role '{role}' for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def suspend_role(user_id: str, role: str) -> bool:
        """Suspend a user's role"""
        try:
            print(f"[USER_ROLE] Suspending role '{role}' for user {user_id}")
            
            await db.update("user_roles", {
                "status": "suspended",
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {
                "user_id": user_id,
                "role": role.lower()
            })
            
            print(f"[USER_ROLE] Role '{role}' suspended successfully for user {user_id}")
            return True
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to suspend role '{role}' for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def activate_role(user_id: str, role: str) -> bool:
        """Activate a user's role"""
        try:
            print(f"[USER_ROLE] Activating role '{role}' for user {user_id}")
            
            await db.update("user_roles", {
                "status": "active",
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {
                "user_id": user_id,
                "role": role.lower()
            })
            
            print(f"[USER_ROLE] Role '{role}' activated successfully for user {user_id}")
            return True
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to activate role '{role}' for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def delete_role(user_id: str, role: str) -> bool:
        """Delete a user's role"""
        try:
            print(f"[USER_ROLE] Deleting role '{role}' for user {user_id}")
            
            await db.delete("user_roles", {
                "user_id": user_id,
                "role": role.lower()
            })
            
            print(f"[USER_ROLE] Role '{role}' deleted successfully for user {user_id}")
            return True
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to delete role '{role}' for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def initialize_user_roles(user_id: str, primary_role: str) -> bool:
        """Initialize user roles with primary role"""
        try:
            print(f"[USER_ROLE] Initializing roles for user {user_id} with primary role '{primary_role}'")
            
            # Create primary role as active and verified
            await UserRoleService.create_user_role(
                user_id=user_id,
                role=primary_role,
                status="active",
                verified=True
            )
            
            print(f"[USER_ROLE] Roles initialized successfully for user {user_id}")
            return True
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to initialize roles for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def add_additional_role(user_id: str, role: str) -> bool:
        """Add an additional role to user (requires admin approval)"""
        try:
            print(f"[USER_ROLE] Adding additional role '{role}' for user {user_id}")
            
            # Check if role already exists
            existing_roles = await UserRoleService.get_user_roles(user_id)
            if any(r.get("role") == role.lower() for r in existing_roles):
                print(f"[USER_ROLE] Role '{role}' already exists for user {user_id}")
                return False
            
            # Create role as pending (requires admin approval)
            await UserRoleService.create_user_role(
                user_id=user_id,
                role=role,
                status="pending",
                verified=False
            )
            
            print(f"[USER_ROLE] Additional role '{role}' added successfully for user {user_id}")
            return True
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to add additional role '{role}' for user {user_id}: {e}")
            return False
    
    @staticmethod
    async def get_user_role_info(user_id: str) -> Dict[str, Any]:
        """Get comprehensive role information for a user"""
        try:
            roles = await UserRoleService.get_user_roles(user_id)
            active_roles = await UserRoleService.get_active_user_roles(user_id)
            
            return {
                "user_id": user_id,
                "all_roles": roles,
                "active_roles": active_roles,
                "has_buyer_access": await UserRoleService.has_role(user_id, "buyer"),
                "has_seller_access": await UserRoleService.has_role(user_id, "seller"),
                "has_agent_access": await UserRoleService.has_role(user_id, "agent"),
                "has_admin_access": await UserRoleService.has_role(user_id, "admin")
            }
            
        except Exception as e:
            print(f"[USER_ROLE] Failed to get role info for user {user_id}: {e}")
            return {
                "user_id": user_id,
                "all_roles": [],
                "active_roles": [],
                "has_buyer_access": False,
                "has_seller_access": False,
                "has_agent_access": False,
                "has_admin_access": False
            }
