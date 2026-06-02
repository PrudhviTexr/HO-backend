from fastapi import APIRouter, HTTPException, Depends, Request, Query, File, UploadFile, Form
from typing import Optional
import traceback
from ..core.security import require_admin_or_api_key
from ..db.supabase_client import db
from ..services.email import send_email

from ..models.schemas import (
    SignupRequest,
    UpdateProfileRequest,
    PropertyRequest,
)
import uuid
import datetime as dt

router = APIRouter()

@router.get("/stats")
async def get_stats(request: Request, _=Depends(require_admin_or_api_key)):
    """Get admin dashboard statistics - optimized with parallel queries and caching"""
    try:
        import asyncio
        import time
        from ..core.cache import cache
        
        start_time = time.time()
        
        # Check cache first (30 second cache)
        cache_key = "admin_stats"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            elapsed = (time.time() - start_time) * 1000
            print(f"[ADMIN] Stats cache hit ({elapsed:.0f}ms)")
            return cached_result
        
        # Execute all count queries in parallel with timeout
        # Note: Each query has a 0.5s timeout in the database client, so total should be < 1s
        try:
            users, properties, bookings, inquiries = await asyncio.wait_for(
                asyncio.gather(
                    db.admin_select("users", select="count"),
                    db.admin_select("properties", select="count"),
                    db.admin_select("bookings", select="count"),
                    db.admin_select("inquiries", select="count"),
                    return_exceptions=True
                ),
                timeout=1.0  # Reduced timeout since DB client has 0.5s timeout for count queries
            )
        except asyncio.TimeoutError:
            print(f"[ADMIN] Stats query timeout")
            # Return cached result if available, otherwise default values
            if cached_result is not None:
                return cached_result
            return {
                "total_users": 0,
                "total_properties": 0,
                "total_bookings": 0,
                "total_inquiries": 0,
            }
        
        # Handle exceptions in individual queries
        users_count = users[0]['count'] if not isinstance(users, Exception) and users else 0
        properties_count = properties[0]['count'] if not isinstance(properties, Exception) and properties else 0
        bookings_count = bookings[0]['count'] if not isinstance(bookings, Exception) and bookings else 0
        inquiries_count = inquiries[0]['count'] if not isinstance(inquiries, Exception) and inquiries else 0
        
        stats = {
            "total_users": users_count,
            "total_properties": properties_count,
            "total_bookings": bookings_count,
            "total_inquiries": inquiries_count,
        }
        
        # Cache result for 60 seconds (longer cache for faster repeated requests)
        cache.set(cache_key, stats, ttl=60)
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[ADMIN] Stats fetched ({elapsed:.0f}ms)")
        
        return stats
    except Exception as e:
        print(f"[ADMIN] Stats error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users")
async def list_users(request: Request, _=Depends(require_admin_or_api_key), limit: int = 100, offset: int = 0):
    """List users - optimized with timeout and pagination"""
    try:
        import asyncio
        import time
        
        start_time = time.time()
        
        # Add timeout to prevent hanging
        try:
            users = await asyncio.wait_for(
                db.admin_select("users", limit=min(limit, 100), offset=offset),
                    timeout=2.0  # 2 second timeout for faster response
            )
        except asyncio.TimeoutError:
            print(f"[ADMIN] Users query timeout")
            return []
        
        result = users or []
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[ADMIN] Users fetched ({elapsed:.0f}ms, {len(result)} users)")
        
        return result
    except Exception as e:
        print(f"[ADMIN] List users error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/all")
async def list_all_users(request: Request, _=Depends(require_admin_or_api_key)):
    """List all users across all roles - no pagination limit"""
    try:
        import asyncio
        
        # Fetch all users without limit (or with a very high limit)
        try:
            users = await asyncio.wait_for(
                db.admin_select("users", limit=10000),  # High limit to get all users
                timeout=5.0  # Longer timeout for large datasets
            )
        except asyncio.TimeoutError:
            print(f"[ADMIN] Users/all query timeout")
            return []
        
        result = users or []
        print(f"[ADMIN] Users/all fetched {len(result)} users")
        return result
    except Exception as e:
        print(f"[ADMIN] List all users error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/{user_id}")
async def get_user(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Get a single user by ID"""
    try:
        user_data = await db.select("users", filters={"id": user_id})
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        return user_data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users")
async def create_user(payload: SignupRequest, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        user_data = {
            "id": str(uuid.uuid4()),
            "email": payload.email,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "user_type": payload.role,
            "created_at": dt.datetime.utcnow().isoformat()
        }
        return await db.insert("users", user_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/users/{user_id}")
async def update_user(user_id: str, payload: UpdateProfileRequest, request: Request, _=Depends(require_admin_or_api_key)):
    """Update user - PATCH method (handles status and verification_status changes)"""
    try:
        update_data = payload.dict(exclude_unset=True)
        
        # Admin override logic for status and verification_status
        # Allow admin to change status independently of verification_status
        if 'verification_status' in update_data:
            if update_data['verification_status'] == 'rejected':
                # User is rejected, set status to inactive if not explicitly set
                if 'status' not in update_data:
                    update_data['status'] = 'inactive'
                # Reset email_verified when rejected
                update_data['email_verified'] = False
                print(f"[ADMIN] User {user_id} set to rejected: email_verified=False, status={update_data.get('status')}")
            elif update_data['verification_status'] == 'verified':
                # When admin sets verification_status to verified, also set email_verified to True
                update_data['email_verified'] = True
                update_data['email_verified_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
                # Set status to active if not explicitly set
                if 'status' not in update_data:
                    update_data['status'] = 'active'
                print(f"[ADMIN] User {user_id} set to verified: email_verified=True, status={update_data.get('status')}")
            elif update_data['verification_status'] == 'pending':
                # User is pending - allow admin to set status independently
                print(f"[ADMIN] User {user_id} set to pending: status={update_data.get('status', 'not changed')}")
        
        # Allow status changes independently
        # Admin can set status to active/inactive regardless of verification_status
        if 'status' in update_data:
            print(f"[ADMIN] User {user_id} status changed to: {update_data['status']}")

        if update_data:
            update_data["updated_at"] = dt.datetime.utcnow().isoformat()
            result = await db.update("users", update_data, {"id": user_id})
            print(f"[ADMIN] User {user_id} updated successfully via PATCH")
            
            # Send email notification for status/verification_status changes (same logic as PUT method)
            try:
                # Get updated user data
                updated_user_data = await db.select("users", filters={"id": user_id})
                if updated_user_data:
                    updated_user = updated_user_data[0]
                    user_email = updated_user.get('email')
                    user_name = f"{updated_user.get('first_name', '')} {updated_user.get('last_name', '')}".strip() or "User"
                    user_type = updated_user.get('user_type', 'user').lower()
                    
                    # Check if status or verification_status changed
                    status_changed = 'status' in update_data
                    verification_changed = 'verification_status' in update_data
                    
                    if status_changed or verification_changed:
                        new_status = update_data.get('status', updated_user.get('status'))
                        new_verification = update_data.get('verification_status', updated_user.get('verification_status'))
                        
                        # Only send email if this is NOT from the approve_user endpoint
                        # The approve_user endpoint sends its own comprehensive email
                        # approve_user always sets both verification_status='verified' AND status='active' together
                        # So if both are being set together, skip email (approve_user will send it)
                        is_approval_action = (
                            verification_changed and 
                            new_verification == 'verified' and 
                            status_changed and 
                            new_status == 'active'
                        )
                        
                        # Use the same email logic as PUT method, but skip if this looks like an approval action
                        # (approve_user endpoint handles its own emails)
                        if new_verification == 'verified' and verification_changed and not is_approval_action:
                            subject = "Your Home & Own Account Has Been Verified"
                            html_content = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <meta charset="utf-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            </head>
                            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                                <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                    <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                                        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Verified!</h1>
                                    </div>
                                    <div style="padding: 40px 30px;">
                                        <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            Congratulations! Your {user_type} account on Home & Own has been verified and is now active.
                                        </p>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            You can now access all features of your account and start using the platform.
                                        </p>
                                        <div style="text-align: center; margin: 40px 0;">
                                            <a href="https://homeandown.com/login" 
                                               style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                      color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                                      font-weight: 600; font-size: 16px;">
                                                Login to Your Account
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            </body>
                            </html>
                            """
                            email_result = await send_email(to=user_email, subject=subject, html=html_content)
                            if email_result.get("status") == "sent":
                                print(f"[ADMIN] ✅ Sent verification email to user: {user_email}")
                            else:
                                print(f"[ADMIN] ⚠️ Failed to send verification email: {email_result.get('error', 'Unknown error')}")
                        elif new_verification == 'rejected' and verification_changed:
                            reason = update_data.get('rejection_reason', 'Not specified')
                            subject = "Update on Your Home & Own Application"
                            html_content = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <meta charset="utf-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            </head>
                            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                                <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                    <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 40px 20px; text-align: center;">
                                        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Application Update</h1>
                                    </div>
                                    <div style="padding: 40px 30px;">
                                        <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            Thank you for your application to Home & Own. After careful review, we regret to inform you that your application has been rejected.
                                        </p>
                                        <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 16px; margin: 30px 0; border-radius: 4px;">
                                            <p style="color: #991b1b; font-size: 14px; margin: 0;"><strong>Reason:</strong> {reason}</p>
                                        </div>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 30px 0 20px 0;">
                                            If you have any questions or would like to appeal this decision, please contact our support team.
                                        </p>
                                    </div>
                                </div>
                            </body>
                            </html>
                            """
                            email_result = await send_email(to=user_email, subject=subject, html=html_content)
                            if email_result.get("status") == "sent":
                                print(f"[ADMIN] ✅ Sent rejection email to user: {user_email}")
                            else:
                                print(f"[ADMIN] ⚠️ Failed to send rejection email: {email_result.get('error', 'Unknown error')}")
                        elif new_status == 'inactive' and status_changed:
                            subject = "Your Home & Own Account Status Update"
                            html_content = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <meta charset="utf-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            </head>
                            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                                <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                    <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 40px 20px; text-align: center;">
                                        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Status Update</h1>
                                    </div>
                                    <div style="padding: 40px 30px;">
                                        <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            Your {user_type} account status has been changed to <strong>Inactive</strong>.
                                        </p>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            If you have any questions about this change, please contact our support team.
                                        </p>
                                    </div>
                                </div>
                            </body>
                            </html>
                            """
                            email_result = await send_email(to=user_email, subject=subject, html=html_content)
                            if email_result.get("status") == "sent":
                                print(f"[ADMIN] ✅ Sent inactive status email to user: {user_email}")
                            else:
                                print(f"[ADMIN] ⚠️ Failed to send inactive status email: {email_result.get('error', 'Unknown error')}")
                        elif new_status == 'active' and status_changed:
                            subject = "Your Home & Own Account Has Been Activated"
                            html_content = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <meta charset="utf-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            </head>
                            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                                <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                    <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                                        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Activated!</h1>
                                    </div>
                                    <div style="padding: 40px 30px;">
                                        <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            Great news! Your {user_type} account has been activated and is now active on Home & Own.
                                        </p>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            You can now access all features of your account.
                                        </p>
                                        <div style="text-align: center; margin: 40px 0;">
                                            <a href="https://homeandown.com/login" 
                                               style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                      color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                                      font-weight: 600; font-size: 16px;">
                                                Login to Your Account
                                            </a>
                                        </div>
                                    </div>
                                </div>
                            </body>
                            </html>
                            """
                            email_result = await send_email(to=user_email, subject=subject, html=html_content)
                            if email_result.get("status") == "sent":
                                print(f"[ADMIN] ✅ Sent activation email to user: {user_email}")
                            else:
                                print(f"[ADMIN] ⚠️ Failed to send activation email: {email_result.get('error', 'Unknown error')}")
            except Exception as email_error:
                import traceback
                print(f"[ADMIN] Error sending status change email: {email_error}")
                print(traceback.format_exc())
                # Don't fail the update if email fails
            
            return result
        return {"message": "No changes to update"}
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error updating user {user_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/users/{user_id}")
async def update_user_put(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Update a user - PUT method (handles status and verification_status changes)"""
    try:
        payload = await request.json()
        if not payload:
            return {"message": "No changes to update"}
        
        update_data = payload.copy()
        
        # Handle status and verification_status changes properly
        # Allow admin to change status independently of verification_status
        if 'verification_status' in update_data:
            if update_data['verification_status'] == 'rejected':
                # When rejected, set email_verified to False
                if 'email_verified' not in update_data:
                    update_data['email_verified'] = False
                # Only set status to inactive if status is not explicitly provided
                if 'status' not in update_data:
                    update_data['status'] = 'inactive'
                print(f"[ADMIN] User {user_id} set to rejected: email_verified=False, status={update_data.get('status')}")
            elif update_data['verification_status'] == 'verified':
                # When verified, set email_verified to True
                if 'email_verified' not in update_data:
                    update_data['email_verified'] = True
                    update_data['email_verified_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
                # Only set status to active if status is not explicitly provided
                if 'status' not in update_data:
                    update_data['status'] = 'active'
                print(f"[ADMIN] User {user_id} set to verified: email_verified=True, status={update_data.get('status')}")
            elif update_data['verification_status'] == 'pending':
                # When set to pending, allow status to be set independently
                print(f"[ADMIN] User {user_id} set to pending: status={update_data.get('status', 'not changed')}")
        
        # Allow status changes independently
        # Admin can set status to active/inactive regardless of verification_status
        if 'status' in update_data:
            print(f"[ADMIN] User {user_id} status changed to: {update_data['status']}")
        
        update_data["updated_at"] = dt.datetime.utcnow().isoformat()
        result = await db.update("users", update_data, {"id": user_id})
        
        # Send email notification for status/verification_status changes
        try:
            # Get updated user data
            updated_user_data = await db.select("users", filters={"id": user_id})
            if updated_user_data:
                updated_user = updated_user_data[0]
                user_email = updated_user.get('email')
                user_name = f"{updated_user.get('first_name', '')} {updated_user.get('last_name', '')}".strip() or "User"
                user_type = updated_user.get('user_type', 'user').lower()
                
                # Check if status or verification_status changed
                status_changed = 'status' in update_data
                verification_changed = 'verification_status' in update_data
                
                if status_changed or verification_changed:
                    new_status = update_data.get('status', updated_user.get('status'))
                    new_verification = update_data.get('verification_status', updated_user.get('verification_status'))
                    
                    # Only send email if this is NOT from the approve_user endpoint
                    # The approve_user endpoint sends its own comprehensive email
                    # approve_user always sets both verification_status='verified' AND status='active' together
                    # So if both are being set together, skip email (approve_user will send it)
                    is_approval_action = (
                        verification_changed and 
                        new_verification == 'verified' and 
                        status_changed and 
                        new_status == 'active'
                    )
                    
                    # Determine email content based on changes, but skip if this looks like an approval action
                    # (approve_user endpoint handles its own emails)
                    if new_verification == 'verified' and verification_changed and not is_approval_action:
                        subject = "Your Home & Own Account Has Been Verified"
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                            <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Verified!</h1>
                                </div>
                                <div style="padding: 40px 30px;">
                                    <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Congratulations! Your {user_type} account on Home & Own has been verified and is now active.
                                    </p>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        You can now access all features of your account and start using the platform.
                                    </p>
                                    <div style="text-align: center; margin: 40px 0;">
                                        <a href="https://homeandown.com/login" 
                                           style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                  color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                                  font-weight: 600; font-size: 16px;">
                                            Login to Your Account
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    elif new_verification == 'rejected' and verification_changed:
                        reason = update_data.get('rejection_reason', 'Not specified')
                        subject = "Update on Your Home & Own Application"
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                            <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 40px 20px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Application Update</h1>
                                </div>
                                <div style="padding: 40px 30px;">
                                    <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Thank you for your application to Home & Own. After careful review, we regret to inform you that your application has been rejected.
                                    </p>
                                    <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 16px; margin: 30px 0; border-radius: 4px;">
                                        <p style="color: #991b1b; font-size: 14px; margin: 0;"><strong>Reason:</strong> {reason}</p>
                                    </div>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 30px 0 20px 0;">
                                        If you have any questions or would like to appeal this decision, please contact our support team.
                                    </p>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    elif new_status == 'inactive' and status_changed:
                        subject = "Your Home & Own Account Status Update"
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                            <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 40px 20px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Status Update</h1>
                                </div>
                                <div style="padding: 40px 30px;">
                                    <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Your {user_type} account status has been changed to <strong>Inactive</strong>.
                                    </p>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        If you have any questions about this change, please contact our support team.
                                    </p>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    elif new_status == 'active' and status_changed:
                        subject = "Your Home & Own Account Has Been Activated"
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                            <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Activated!</h1>
                                </div>
                                <div style="padding: 40px 30px;">
                                    <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Great news! Your {user_type} account has been activated and is now active.
                                    </p>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        You can now access all features of your account.
                                    </p>
                                    <div style="text-align: center; margin: 40px 0;">
                                        <a href="https://homeandown.com/login" 
                                           style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                  color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                                  font-weight: 600; font-size: 16px;">
                                            Login to Your Account
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    else:
                        # Generic status update
                        subject = "Your Home & Own Account Status Update"
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                            <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 40px 20px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Status Update</h1>
                                </div>
                                <div style="padding: 40px 30px;">
                                    <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Your {user_type} account status has been updated.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #2563eb; padding: 16px; margin: 30px 0; border-radius: 4px;">
                                        <p style="color: #1e293b; font-size: 14px; margin: 5px 0;"><strong>Status:</strong> {new_status or 'N/A'}</p>
                                        <p style="color: #1e293b; font-size: 14px; margin: 5px 0;"><strong>Verification:</strong> {new_verification or 'N/A'}</p>
                                    </div>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                    
                    if user_email and (status_changed or verification_changed):
                        email_result = await send_email(to=user_email, subject=subject, html=html_content)
                        if email_result.get("status") == "sent":
                            print(f"[ADMIN] ✅ Sent status update email to user: {user_email}")
                        else:
                            print(f"[ADMIN] ⚠️ Failed to send status update email: {email_result.get('error', 'Unknown error')}")
                            print(f"[ADMIN] Email result: {email_result}")
        except Exception as email_error:
            print(f"[ADMIN] ⚠️ Failed to send status update email: {email_error}")
            import traceback
            print(traceback.format_exc())
            # Don't fail the update if email fails
        
        print(f"[ADMIN] User {user_id} updated successfully")
        
        # Return updated user data for frontend refresh
        updated_user_data = await db.select("users", filters={"id": user_id})
        if updated_user_data:
            return updated_user_data[0]
        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error updating user {user_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        await db.delete("users", {"id": user_id})
        return {"success": True, "message": "User deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/properties")
async def list_properties(request: Request, _=Depends(require_admin_or_api_key), limit: int = 2000, offset: int = 0):
    """List properties - optimized with timeout, pagination, and parallel queries"""
    try:
        import asyncio
        import time
        
        start_time = time.time()
        
        # Execute queries in parallel with timeout
        # Note: Each query has a 2s timeout in the database client
        try:
            properties, users = await asyncio.wait_for(
                asyncio.gather(
                    db.admin_select("properties", limit=min(limit, 5000), offset=offset, order_by="created_at", ascending=False),
                    db.admin_select("users", limit=1000, order_by="created_at", ascending=False),  # Limit users to prevent huge fetch
                    return_exceptions=True
                ),
                timeout=1.5  # Reduced timeout since DB client has 1s timeout for count queries
            )
        except asyncio.TimeoutError:
            print(f"[ADMIN] Properties query timeout")
            return []
        
        # Handle exceptions
        if isinstance(properties, Exception):
            print(f"[ADMIN] Properties query error: {properties}")
            properties = []
        if isinstance(users, Exception):
            print(f"[ADMIN] Users query error: {users}")
            users = []
        
        if not properties:
            properties = []
        if not users:
            users = []
        
        # Build user map with full names (not IDs)
        user_map = {}
        for user in users:
            user_id = user.get('id')
            if not user_id:
                continue
                
            first_name = user.get('first_name', '').strip()
            last_name = user.get('last_name', '').strip()
            full_name = f"{first_name} {last_name}".strip()
            
            # Prefer full name, fallback to first name only, then email, then custom_id
            if full_name:
                user_map[user_id] = full_name
            elif first_name:
                user_map[user_id] = first_name
            elif user.get('email'):
                user_map[user_id] = user.get('email', 'Unknown User')
            elif user.get('custom_id'):
                user_map[user_id] = f"User {user.get('custom_id')}"
            else:
                user_map[user_id] = 'Unknown User'
        
        if properties:
            for prop in properties:
                # Get owner name - check owner_id first, then added_by (who created it)
                owner_id = prop.get('owner_id') or prop.get('added_by')
                if owner_id and owner_id in user_map:
                    owner_name = user_map[owner_id]
                elif owner_id:
                    # If ID exists but not in map, try to fetch or use ID
                    owner_name = f"User {owner_id[:8]}..."
                else:
                    owner_name = 'N/A'
                
                prop['owner_name'] = owner_name
                
                # Get seller name - check seller_id separately
                seller_id = prop.get('seller_id')
                if seller_id and seller_id in user_map:
                    seller_name = user_map[seller_id]
                elif seller_id:
                    seller_name = f"Seller {seller_id[:8]}..."
                else:
                    seller_name = 'N/A'
                
                prop['seller_name'] = seller_name
                
                # Get agent name - check assigned_agent_id first, then agent_id
                agent_id = prop.get('assigned_agent_id') or prop.get('agent_id')
                if agent_id and agent_id in user_map:
                    agent_name = user_map[agent_id]
                elif agent_id:
                    # If ID exists but not in map, use ID
                    agent_name = f"Agent {agent_id[:8]}..."
                else:
                    agent_name = 'Unassigned'
                
                prop['agent_name'] = agent_name
                
                # For sold properties, get buyer name from inquiries
                if prop.get('status', '').lower() == 'sold':
                    try:
                        # Fetch the most recent completed inquiry for this property
                        inquiries = await db.select(
                            "inquiries",
                            filters={"property_id": prop.get('id')},
                            limit=1,
                            order_by="created_at",
                            ascending=False
                        )
                        if inquiries:
                            inquiry = inquiries[0]
                            # Check if inquiry message contains buyer name (format: "[Property Sold] Buyer: Name")
                            message = inquiry.get('message', '')
                            if '[Property Sold]' in message or 'Buyer:' in message:
                                # Extract buyer name from message
                                import re
                                buyer_match = re.search(r'Buyer:\s*([^\n]+)', message, re.IGNORECASE)
                                if buyer_match:
                                    prop['buyer_name'] = buyer_match.group(1).strip()
                                else:
                                    # Fallback to inquiry name
                                    prop['buyer_name'] = inquiry.get('name', 'Unknown Buyer')
                            else:
                                # Use inquiry name as buyer
                                prop['buyer_name'] = inquiry.get('name', 'Unknown Buyer')
                    except Exception as buyer_error:
                        print(f"[ADMIN] Could not fetch buyer info for property {prop.get('id')}: {buyer_error}")
                        prop['buyer_name'] = None
                
                # Process images field - handle JSON strings and arrays
                import json
                images = prop.get('images')
                if images is None:
                    prop['images'] = []
                elif isinstance(images, str):
                    try:
                        parsed = json.loads(images)
                        prop['images'] = parsed if isinstance(parsed, list) else []
                    except (json.JSONDecodeError, TypeError):
                        prop['images'] = []
                elif not isinstance(images, list):
                    prop['images'] = []
                
                # Process amenities field similarly
                amenities = prop.get('amenities')
                if amenities is None:
                    prop['amenities'] = []
                elif isinstance(amenities, str):
                    try:
                        parsed = json.loads(amenities)
                        prop['amenities'] = parsed if isinstance(parsed, list) else []
                    except (json.JSONDecodeError, TypeError):
                        prop['amenities'] = []
                elif not isinstance(amenities, list):
                    prop['amenities'] = []
                
                # Debug logging for first property
                if properties.index(prop) == 0:
                    print(f"[ADMIN] Property {prop.get('id')[:8]}: owner_id={owner_id}, owner_name={owner_name}, agent_id={agent_id}, agent_name={agent_name}, images_count={len(prop.get('images', []))}")
        
        print(f"[ADMIN] Returning {len(properties) if properties else 0} properties with owner/agent names")
        return properties or []
    except Exception as e:
        print(f"[ADMIN] Error in list_properties: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/properties")
async def create_property(payload: PropertyRequest, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        property_data = payload.dict()
        property_data["id"] = str(uuid.uuid4())
        property_data["created_at"] = dt.datetime.utcnow().isoformat()
        
        # Ensure properties created via admin also require approval
        property_data.setdefault("status", "pending")
        property_data.setdefault("verified", False)
        property_data.setdefault("featured", False)
        
        return await db.insert("properties", property_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/properties/{property_id}")
async def update_property(property_id: str, payload: PropertyRequest, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        update_data = payload.dict(exclude_unset=True)
        if update_data:
            update_data["updated_at"] = dt.datetime.utcnow().isoformat()
            return await db.update("properties", update_data, {"id": property_id})
        return {"message": "No changes to update"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/properties/{property_id}")
async def delete_property(property_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        await db.delete("properties", {"id": property_id})
        return {"success": True, "message": "Property deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/properties/{property_id}/approve")
async def approve_property(property_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        update_data = {
            "verified": True, 
            "status": "active",  # Changed from "verified" to "active" so property is visible
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("properties", update_data, {"id": property_id})
        
        # Send approval email
        try:
            property_data = await db.select("properties", filters={"id": property_id})
            if property_data:
                prop = property_data[0]
                owner_id = prop.get('owner_id')
                if owner_id:
                    user_data = await db.select("users", filters={"id": owner_id})
                    if user_data:
                        user = user_data[0]
                        subject = f"Your property listing '{prop.get('title')}' has been approved"
                        html_content = f"<p>Hi {user.get('first_name')},</p><p>Congratulations! Your property listing, <strong>{prop.get('title')}</strong>, has been approved and is now live on Home & Own.</p>"
                        await send_email(to=user.get('email'), subject=subject, html=html_content)
        except Exception as email_error:
            print(f"[ADMIN] !!! Failed to send property approval email: {email_error}")

        # Start sequential agent notification queue
        print(f"[ADMIN] ========== STARTING AGENT NOTIFICATION PROCESS ==========")
        print(f"[ADMIN] Property ID: {property_id}")
        try:
            # Get property details for logging
            property_data = await db.select("properties", filters={"id": property_id})
            if property_data:
                prop = property_data[0]
                print(f"[ADMIN] Property Title: {prop.get('title')}")
                print(f"[ADMIN] Property Zipcode: {prop.get('zip_code')}")
                print(f"[ADMIN] Property City: {prop.get('city')}")
                print(f"[ADMIN] Property State: {prop.get('state')}")
            
            from ..services.sequential_agent_notification import SequentialAgentNotificationService
            print(f"[ADMIN] Calling SequentialAgentNotificationService.start_property_assignment_queue()")
            queue_result = await SequentialAgentNotificationService.start_property_assignment_queue(property_id)
            
            print(f"[ADMIN] Queue result: {queue_result}")
            
            if not queue_result.get("success"):
                print(f"[ADMIN] ⚠️ WARNING: Failed to start agent notification queue")
                print(f"[ADMIN] Error: {queue_result.get('error')}")
                print(f"[ADMIN] Unassigned: {queue_result.get('unassigned', False)}")
                # Don't fail the approval if notification queue fails - property is still approved
            else:
                print(f"[ADMIN] ✅ SUCCESS: Agent notification queue started")
                print(f"[ADMIN] Agents count: {queue_result.get('agents_count')}")
                print(f"[ADMIN] Queue ID: {queue_result.get('queue_id')}")
        except Exception as notification_error:
            print(f"[ADMIN] !!! CRITICAL: Failed to start agent notification queue")
            print(f"[ADMIN] Exception: {notification_error}")
            # Property is still approved, this is a warning
            import traceback
            print(f"[ADMIN] Full traceback:")
            print(traceback.format_exc())
        
        print(f"[ADMIN] ========== AGENT NOTIFICATION PROCESS COMPLETE ==========")


        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] !!! Error approving property {property_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/properties/{property_id}/reject")
async def reject_property(property_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        payload = await request.json() if request else {}
        reason = payload.get("reason", "Rejected by admin")
        
        # Note: properties table doesn't have rejection_reason column
        # We'll just update status and verified fields, and store reason in description or notes if available
        update_data = {
            "verified": False,
            "status": "rejected",
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        # Try to append rejection reason to description if it exists
        # First, get current property to check if description exists
        try:
            current_property = await db.select("properties", filters={"id": property_id})
            if current_property and current_property[0].get("description"):
                current_desc = current_property[0].get("description", "")
                update_data["description"] = f"{current_desc}\n\n[REJECTED: {reason}]"
            # If description doesn't exist or is empty, we'll just update status
        except Exception as desc_error:
            print(f"[ADMIN] Could not update description with rejection reason: {desc_error}")
        
        print(f"[ADMIN] Rejecting property {property_id} with reason: {reason}")
        result = await db.update("properties", update_data, {"id": property_id})
        print(f"[ADMIN] Property rejection result: {result}")
        
        # Send rejection email
        try:
            property_data = await db.select("properties", filters={"id": property_id})
            if property_data:
                prop = property_data[0]
                owner_id = prop.get('owner_id')
                if owner_id:
                    user_data = await db.select("users", filters={"id": owner_id})
                    if user_data:
                        user = user_data[0]
                        subject = f"An update on your property listing '{prop.get('title')}'"
                        html_content = f"<p>Hi {user.get('first_name')},</p><p>We have reviewed your property listing, <strong>{prop.get('title')}</strong>. We regret to inform you that it has been rejected.</p><p><strong>Reason:</strong> {reason}</p>"
                        email_result = await send_email(to=user.get('email'), subject=subject, html=html_content)
                        if email_result.get("status") == "sent":
                            print(f"[ADMIN] ✅ Sent property rejection email to: {user.get('email')}")
                        else:
                            print(f"[ADMIN] ⚠️ Failed to send property rejection email: {email_result.get('error', 'Unknown error')}")
                            print(f"[ADMIN] Email result: {email_result}")
        except Exception as email_error:
            print(f"[ADMIN] !!! Exception sending property rejection email: {email_error}")
            import traceback
            print(traceback.format_exc())

        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] !!! Error rejecting property {property_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
        
@router.post("/properties/{property_id}/resubmit")
async def resubmit_property(property_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        payload = await request.json() if request else {}
        reason = payload.get("reason", "Resubmission requested")
        
        # Note: properties table doesn't have rejection_reason column
        update_data = {
            "status": "pending",  # Change status to pending for resubmission
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        # Try to append resubmission reason to description if it exists
        try:
            current_property = await db.select("properties", filters={"id": property_id})
            if current_property and current_property[0].get("description"):
                current_desc = current_property[0].get("description", "")
                update_data["description"] = f"{current_desc}\n\n[RESUBMITTED: {reason}]"
        except Exception as desc_error:
            print(f"[ADMIN] Could not update description with resubmission reason: {desc_error}")
        
        print(f"[ADMIN] Resubmitting property {property_id} with reason: {reason}")
        result = await db.update("properties", update_data, {"id": property_id})
        print(f"[ADMIN] Property resubmission result: {result}")

        # Send resubmission request email
        try:
            property_data = await db.select("properties", filters={"id": property_id})
            if property_data:
                prop = property_data[0]
                owner_id = prop.get('owner_id')
                if owner_id:
                    user_data = await db.select("users", filters={"id": owner_id})
                    if user_data:
                        user = user_data[0]
                        subject = f"Action required for your property listing '{prop.get('title')}'"
                        html_content = f"<p>Hi {user.get('first_name')},</p><p>Regarding your property listing, <strong>{prop.get('title')}</strong>, we require some changes before it can be approved.</p><p><strong>Reason:</strong> {reason}</p><p>Please log in to your account to edit and resubmit your property for review.</p>"
                        email_result = await send_email(to=user.get('email'), subject=subject, html=html_content)
                        if email_result.get("status") == "sent":
                            print(f"[ADMIN] ✅ Sent property resubmission email to: {user.get('email')}")
                        else:
                            print(f"[ADMIN] ⚠️ Failed to send property resubmission email: {email_result.get('error', 'Unknown error')}")
                            print(f"[ADMIN] Email result: {email_result}")
        except Exception as email_error:
            print(f"[ADMIN] !!! Exception sending property resubmission email: {email_error}")
            import traceback
            print(traceback.format_exc())

        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] !!! Error setting property to resubmit {property_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/properties/{property_id}/assign-agent")
async def assign_agent(property_id: str, payload: dict, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        agent_id = payload.get("agent_id")
        
        if not agent_id:
            raise HTTPException(status_code=400, detail="agent_id is required")
        
        # Also set assigned_agent_id for consistency
        update_data = {
            "agent_id": agent_id,
            "assigned_agent_id": agent_id,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("properties", update_data, {"id": property_id})
        
        # Verify the update was successful
        if result:
            print(f"[ADMIN] ✅ Successfully assigned agent {agent_id} to property {property_id}")
            print(f"[ADMIN] Update result: {result}")
            # Double-check by querying the property
            verify_property = await db.select("properties", filters={"id": property_id})
            if verify_property:
                print(f"[ADMIN] Verification - Property agent_id: {verify_property[0].get('agent_id')}")
                print(f"[ADMIN] Verification - Property assigned_agent_id: {verify_property[0].get('assigned_agent_id')}")
        else:
            print(f"[ADMIN] ⚠️ Warning: Update returned empty result for property {property_id}")

        # Send email notifications to BOTH agent and property owner/seller
        try:
            property_data = await db.select("properties", filters={"id": property_id})
            agent_data = await db.select("users", filters={"id": agent_id})
            
            if property_data and agent_data:
                prop = property_data[0]
                agent = agent_data[0]
                agent_name = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip() or "Agent"
                agent_email = agent.get('email')
                agent_phone = agent.get('phone_number', 'N/A')
                agent_license = agent.get('agent_license_number') or agent.get('license_number') or agent.get('custom_id', 'N/A')
                
                # Get property owner/seller information
                owner_id = prop.get('owner_id') or prop.get('seller_id')
                owner_data = None
                owner_email = None
                owner_name = None
                if owner_id:
                    owner_records = await db.select("users", filters={"id": owner_id})
                    if owner_records:
                        owner_data = owner_records[0]
                        owner_email = owner_data.get('email')
                        owner_name = f"{owner_data.get('first_name', '')} {owner_data.get('last_name', '')}".strip() or "Property Owner"
                
                # Send email to AGENT
                if agent_email:
                    try:
                        from ..services.templates import get_property_assignment_email
                        html_content = await get_property_assignment_email(
                            agent_name=agent_name,
                            property_title=prop.get('title', 'Property'),
                            property_id=property_id,
                            property_address=prop.get('address', prop.get('city', 'N/A')),
                            property_price=prop.get('price') or prop.get('monthly_rent', 'N/A')
                        )
                        subject = f"New Property Assignment: {prop.get('title', 'Property')} - Home & Own"
                        email_result = await send_email(to=agent_email, subject=subject, html=html_content)
                        if email_result.get("status") == "sent":
                            print(f"[ADMIN] ✅ Sent agent assignment email to: {agent_email}")
                        else:
                            print(f"[ADMIN] ⚠️ Failed to send agent assignment email: {email_result.get('error', 'Unknown error')}")
                            print(f"[ADMIN] Email result: {email_result}")
                    except Exception as template_error:
                        import traceback
                        print(f"[ADMIN] Email template error, using fallback: {template_error}")
                        print(traceback.format_exc())
                        # Fallback email for agent
                        subject = f"You have been assigned to a new property: {prop.get('title')}"
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                            <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 40px 20px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">New Property Assignment</h1>
                                </div>
                                <div style="padding: 40px 30px;">
                                    <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {agent_name},</h2>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        You have been assigned as the agent for a new property on Home & Own.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #2563eb; padding: 20px; margin: 30px 0; border-radius: 4px;">
                                        <p style="color: #1e293b; font-size: 18px; font-weight: 600; margin: 0 0 10px 0;">{prop.get('title', 'Property')}</p>
                                        <p style="color: #475569; font-size: 14px; margin: 5px 0;"><strong>Address:</strong> {prop.get('address', prop.get('city', 'N/A'))}</p>
                                        {f'<p style="color: #475569; font-size: 14px; margin: 5px 0;"><strong>Price:</strong> ₹{prop.get("price"):,}</p>' if prop.get('price') else ''}
                                        {f'<p style="color: #475569; font-size: 14px; margin: 5px 0;"><strong>Monthly Rent:</strong> ₹{prop.get("monthly_rent"):,}/month</p>' if prop.get('monthly_rent') else ''}
                                    </div>
                                    <div style="text-align: center; margin: 40px 0;">
                                    <a href="https://homeandown.com/agent/dashboard" 
                                           style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                  color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                                  font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);">
                                        View Dashboard
                                    </a>
                                </div>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                        email_result = await send_email(to=agent_email, subject=subject, html=html_content)
                        if email_result.get("status") == "sent":
                            print(f"[ADMIN] ✅ Sent fallback agent assignment email to: {agent_email}")
                        else:
                            print(f"[ADMIN] ⚠️ Failed to send agent assignment email: {email_result.get('error', 'Unknown error')}")
                            print(f"[ADMIN] Email result: {email_result}")
                else:
                    print(f"[ADMIN] ⚠️ Agent email not found for agent_id: {agent_id}")
                
                # Send email to PROPERTY OWNER/SELLER with agent contact details
                if owner_email:
                    try:
                        subject = f"Agent Assigned to Your Property: {prop.get('title', 'Property')} - Home & Own"
                        html_content = f"""
                        <!DOCTYPE html>
                        <html>
                        <head>
                            <meta charset="utf-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
                        </head>
                        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                            <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Agent Assigned to Your Property</h1>
                                </div>
                                <div style="padding: 40px 30px;">
                                    <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {owner_name},</h2>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Great news! An agent has been assigned to your property listing on Home & Own.
                                    </p>
                                    <div style="background-color: #f0f9ff; border-left: 4px solid #2563eb; padding: 20px; margin: 30px 0; border-radius: 4px;">
                                        <p style="color: #1e293b; font-size: 18px; font-weight: 600; margin: 0 0 15px 0;">Your Property</p>
                                        <p style="color: #475569; font-size: 14px; margin: 5px 0;"><strong>Title:</strong> {prop.get('title', 'Property')}</p>
                                        <p style="color: #475569; font-size: 14px; margin: 5px 0;"><strong>Address:</strong> {prop.get('address', prop.get('city', 'N/A'))}</p>
                                    </div>
                                    <div style="background-color: #d1fae5; border-left: 4px solid #10b981; padding: 20px; margin: 30px 0; border-radius: 4px;">
                                        <p style="color: #065f46; font-size: 18px; font-weight: 600; margin: 0 0 15px 0;">Assigned Agent Details</p>
                                        <p style="color: #065f46; font-size: 14px; margin: 5px 0;"><strong>Name:</strong> {agent_name}</p>
                                        <p style="color: #065f46; font-size: 14px; margin: 5px 0;"><strong>Email:</strong> <a href="mailto:{agent_email}" style="color: #059669; text-decoration: none;">{agent_email}</a></p>
                                        <p style="color: #065f46; font-size: 14px; margin: 5px 0;"><strong>Phone:</strong> <a href="tel:{agent_phone}" style="color: #059669; text-decoration: none;">{agent_phone}</a></p>
                                        {f'<p style="color: #065f46; font-size: 14px; margin: 5px 0;"><strong>License Number:</strong> {agent_license}</p>' if agent_license != 'N/A' else ''}
                                    </div>
                                    <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 30px 0 20px 0;">
                                        Your assigned agent will help you manage inquiries, bookings, and property viewings. Feel free to contact them directly using the information above.
                                    </p>
                                    <div style="text-align: center; margin: 40px 0;">
                                        <a href="https://homeandown.com/login" 
                                           style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                                  color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                                  font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);">
                                            View Your Property
                                        </a>
                                    </div>
                                </div>
                                <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                                    <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The Home & Own Team</strong>
                                    </p>
                                </div>
                            </div>
                        </body>
                        </html>
                        """
                        email_result = await send_email(to=owner_email, subject=subject, html=html_content)
                        if email_result.get("status") == "sent":
                            print(f"[ADMIN] ✅ Sent property assignment notification to owner/seller: {owner_email}")
                        else:
                            print(f"[ADMIN] ⚠️ Failed to send email to property owner: {email_result.get('error', 'Unknown error')}")
                            print(f"[ADMIN] Email result: {email_result}")
                    except Exception as owner_email_error:
                        print(f"[ADMIN] ⚠️ Exception sending email to property owner: {owner_email_error}")
                        import traceback
                        print(traceback.format_exc())
                else:
                    print(f"[ADMIN] ⚠️ Property owner email not found (owner_id: {owner_id})")
            else:
                print(f"[ADMIN] ⚠️ Property or agent not found")
        except Exception as email_error:
            print(f"[ADMIN] !!! Failed to send assignment emails: {email_error}")
            import traceback
            print(traceback.format_exc())
            # Don't fail the assignment if email fails

        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] !!! Error assigning agent to {property_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/bookings")
async def list_bookings(request: Request, _=Depends(require_admin_or_api_key), limit: int = 100, offset: int = 0):
    """List bookings - optimized with timeout, pagination, and parallel queries"""
    try:
        import asyncio
        import time
        
        start_time = time.time()
        
        # Execute queries in parallel with timeout
        # Note: Each query has a 2s timeout in the database client
        try:
            bookings, properties, users = await asyncio.wait_for(
                asyncio.gather(
                    db.admin_select("bookings", limit=min(limit, 200), offset=offset, order_by="created_at", ascending=False),
                    db.admin_select("properties", limit=500, order_by="created_at", ascending=False),  # Limit to prevent huge fetch
                    db.admin_select("users", limit=1000, order_by="created_at", ascending=False),  # Limit to prevent huge fetch
                    return_exceptions=True
                ),
                timeout=1.5  # Reduced timeout since DB client has 1s timeout for count queries
            )
        except asyncio.TimeoutError:
            print(f"[ADMIN] Bookings query timeout")
            return []
        
        # Handle exceptions
        if isinstance(bookings, Exception):
            print(f"[ADMIN] Bookings query error: {bookings}")
            bookings = []
        if isinstance(properties, Exception):
            print(f"[ADMIN] Properties query error: {properties}")
            properties = []
        if isinstance(users, Exception):
            print(f"[ADMIN] Users query error: {users}")
            users = []
        
        if not bookings:
            bookings = []
        if not properties:
            properties = []
        if not users:
            users = []

        user_map = {user['id']: f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() for user in users}
        property_map = {prop['id']: prop for prop in properties}
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[ADMIN] Bookings data fetched ({elapsed:.0f}ms)")

        for booking in bookings:
            # Get customer name from user_id or booking fields
            customer_name = user_map.get(booking.get('user_id'), None)
            if not customer_name:
                # Fallback to booking name field if user not found
                customer_name = booking.get('name') or 'N/A'
            booking['customer_name'] = customer_name
            
            # Get property information
            property_info = property_map.get(booking.get('property_id'))
            if property_info:
                booking['property_title'] = property_info.get('title', 'N/A')
            else:
                booking['property_title'] = 'N/A'
            
            # Get agent name - prioritize booking.agent_id over property.agent_id
            agent_id = booking.get('agent_id')  # First check booking's direct agent assignment
            if not agent_id and property_info:
                agent_id = property_info.get('agent_id') or property_info.get('assigned_agent_id')  # Fallback to property agent
            booking['agent_name'] = user_map.get(agent_id, 'Unassigned') if agent_id else 'Unassigned'
            booking['agent_id'] = agent_id  # Ensure agent_id is included in response
        
        return bookings
    except Exception as e:
        import traceback
        print(f"[ADMIN] !!! Error listing bookings: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/inquiries")
async def list_inquiries(request: Request, _=Depends(require_admin_or_api_key), limit: int = 100, offset: int = 0):
    """List inquiries - optimized with timeout and pagination"""
    try:
        import asyncio
        import time
        
        start_time = time.time()
        
        # Add timeout to prevent hanging
        # Note: Query has a 2s timeout in the database client
        try:
            inquiries = await asyncio.wait_for(
                db.admin_select("inquiries", limit=min(limit, 200), offset=offset, order_by="created_at", ascending=False),
                timeout=2.0  # Reduced timeout since DB client has 1.5s timeout
            )
        except asyncio.TimeoutError:
            print(f"[ADMIN] Inquiries query timeout")
            return []
        
        result = inquiries or []
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[ADMIN] Inquiries fetched ({elapsed:.0f}ms, {len(result)} inquiries)")
        
        return result
    except Exception as e:
        print(f"[ADMIN] List inquiries error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/fix-status-mismatch")
async def fix_status_mismatch(request: Request, _=Depends(require_admin_or_api_key)):
    """Fix users who have verification_status='verified' but status='pending'"""
    try:
        # Find all users with mismatch
        all_users = await db.admin_select("users")
        fixed_count = 0
        
        for user in all_users:
            verification_status = (user.get('verification_status') or '').lower()
            status = (user.get('status') or '').lower()
            
            # If verified but status is pending, fix it
            if verification_status == 'verified' and status in ['pending', '', None]:
                await db.update("users", {
                    "status": "active",
                    "updated_at": dt.datetime.utcnow().isoformat()
                }, {"id": user['id']})
                fixed_count += 1
                print(f"[ADMIN] Fixed status for user {user.get('id')[:8]}: {user.get('email')}")
        
        return {
            "success": True,
            "message": f"Fixed {fixed_count} users with status mismatch",
            "fixed_count": fixed_count
        }
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error fixing status mismatch: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fix status mismatch: {str(e)}")

@router.post("/users/{user_id}/approve")
async def approve_user(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        # Get user data first to check user type
        user_data = await db.select("users", filters={"id": user_id})
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = user_data[0]
        user_type = user.get('user_type', '').lower()
        
        update_data = {
            "verification_status": "verified",
            "status": "active",  # Ensure status is set to 'active' not 'pending'
            "email_verified": True,  # Set email_verified to True when admin approves
            "email_verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        # For agents, ensure license number is set after approval
        if user_type == 'agent':
            # Get or generate license number
            license_number = user.get('agent_license_number') or user.get('license_number') or user.get('custom_id')
            if not license_number:
                # Generate new license number
                try:
                    from ..services.admin_service import generate_custom_id
                    license_number = await generate_custom_id('agent')
                    print(f"[ADMIN] Generated new license number: {license_number}")
                except Exception as gen_error:
                    print(f"[ADMIN] Failed to generate license number: {gen_error}")
                    # Fallback to simple format
                    import time
                    license_number = f"AGT{int(time.time())%1000000:06d}"
                
                # Set license number in all possible fields for compatibility
                update_data['agent_license_number'] = license_number
                update_data['license_number'] = license_number
                update_data['custom_id'] = license_number  # Also update custom_id
                print(f"[ADMIN] Set license number for agent {user_id}: {license_number}")
            else:
                # Ensure license number is in all fields
                update_data['agent_license_number'] = license_number
                update_data['license_number'] = license_number
                if not user.get('custom_id'):
                    update_data['custom_id'] = license_number
                print(f"[ADMIN] Using existing license number for agent {user_id}: {license_number}")
        
        # For buyers and sellers, ensure license number is set to null or 'NA'
        elif user_type in ['buyer', 'seller']:
            # Explicitly set to None or remove if exists
            update_data['agent_license_number'] = None
            update_data['license_number'] = None
            print(f"[ADMIN] Cleared license number for {user_type} {user_id}")
        
        # Mark that this is an approval action to prevent duplicate emails from PUT/PATCH endpoints
        # We'll add a flag to the update_data to indicate this is from the approve endpoint
        result = await db.update("users", update_data, {"id": user_id})

        # Send comprehensive approval email (only from approve_user endpoint, not from PUT/PATCH)
        try:
            updated_user_data = await db.select("users", filters={"id": user_id})
            if updated_user_data:
                updated_user = updated_user_data[0]
                license_number = updated_user.get('agent_license_number') or updated_user.get('license_number')
                user_email = updated_user.get('email')
                user_name = f"{updated_user.get('first_name', '')} {updated_user.get('last_name', '')}".strip() or "User"
                user_type_display = {
                    'agent': 'Agent',
                    'seller': 'Seller',
                    'buyer': 'Buyer',
                    'admin': 'Administrator'
                }.get(user_type, user_type.title())
                
                subject = f"Your Home & Own {user_type_display} Account Has Been Approved"
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                    <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                            <div style="width: 60px; height: 60px; background-color: white; border-radius: 50%; margin: 0 auto 20px; display: flex; align-items: center; justify-content: center;">
                                <span style="font-size: 30px; color: #10b981;">✓</span>
                            </div>
                            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Account Approved!</h1>
                        </div>
                        <div style="padding: 40px 30px;">
                            <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Congratulations {user_name}!</h2>
                            <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                Your {user_type_display} account on Home & Own has been approved and is now active.
                            </p>
                            {f'<div style="background-color: #d1fae5; border-left: 4px solid #10b981; padding: 16px; margin: 30px 0; border-radius: 4px;"><p style="color: #065f46; font-size: 14px; margin: 0;"><strong>Your License Number:</strong> {license_number}</p></div>' if user_type == 'agent' and license_number else ''}
                            <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 30px 0 20px 0;">
                                You can now log in and access your dashboard to start using all features of the platform.
                            </p>
                            <div style="text-align: center; margin: 40px 0;">
                                <a href="https://homeandown.com/login" 
                                   style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                          color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                          font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);">
                                    Login to Your Account
                                </a>
                            </div>
                            <div style="background-color: #f8fafc; border-radius: 8px; padding: 20px; margin: 30px 0;">
                                <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0; line-height: 1.6;">
                                    <strong>What you can do now:</strong>
                                </p>
                                <ul style="color: #64748b; font-size: 14px; margin: 0; padding-left: 20px; line-height: 1.8;">
                                    <li>Access your {user_type_display.lower()} dashboard</li>
                                    <li>Manage your profile and settings</li>
                                    {f'<li>View and manage assigned properties</li>' if user_type == 'agent' else ''}
                                    {f'<li>List and manage your properties</li>' if user_type == 'seller' else ''}
                                    {f'<li>Browse and save properties</li>' if user_type == 'buyer' else ''}
                                    <li>Contact support if you need assistance</li>
                                </ul>
                            </div>
                        </div>
                        <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                            <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                                Welcome to Home & Own!<br>
                                <strong>The Home & Own Team</strong>
                            </p>
                        </div>
                    </div>
                </body>
                </html>
                """
                email_result = await send_email(to=user_email, subject=subject, html=html_content)
                if email_result.get("status") == "sent":
                    print(f"[ADMIN] ✅ Sent comprehensive approval email to: {user_email}")
                else:
                    print(f"[ADMIN] ⚠️ Failed to send approval email: {email_result.get('error', 'Unknown error')}")
                    print(f"[ADMIN] Email result: {email_result}")
        except Exception as email_error:
            print(f"[ADMIN] !!! Exception sending approval email: {email_error}")
            import traceback
            print(traceback.format_exc())

        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] !!! Error approving user {user_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/users/{user_id}/reject")
async def reject_user(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    try:
        payload = await request.json()
        reason = payload.get("reason", "Rejected by admin")
        update_data = {
            "verification_status": "rejected", "status": "inactive", "rejection_reason": reason,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("users", update_data, {"id": user_id})
        
        # Send rejection email
        try:
            user_data = await db.select("users", filters={"id": user_id})
            if user_data:
                user = user_data[0]
                subject = "An update on your Home & Own application"
                html_content = f"<p>Hi {user.get('first_name')},</p><p>Thank you for your application to Home & Own. After careful review, we regret to inform you that your application has been rejected.</p><p><strong>Reason:</strong> {reason}</p>"
                email_result = await send_email(to=user.get('email'), subject=subject, html=html_content)
                if email_result.get("status") == "sent":
                    print(f"[ADMIN] ✅ Sent rejection email to: {user.get('email')}")
                else:
                    print(f"[ADMIN] ⚠️ Failed to send rejection email: {email_result.get('error', 'Unknown error')}")
                    print(f"[ADMIN] Email result: {email_result}")
        except Exception as email_error:
            print(f"[ADMIN] !!! Exception sending rejection email: {email_error}")
            import traceback
            print(traceback.format_exc())
        
        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] !!! Error rejecting user {user_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/documents")
async def list_documents(
    request: Request,
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    _=Depends(require_admin_or_api_key)
):
    """List documents with optional filtering"""
    try:
        print(f"[ADMIN] Fetching documents with entity_type={entity_type}, entity_id={entity_id}")
        
        # Build filters if provided
        filters = {}
        if entity_id:
            filters['entity_id'] = entity_id
        
        # Handle entity_type: if searching for 'user', also include 'user_documents' for backwards compatibility
        if entity_type:
            if entity_type == 'user':
                # Query for both 'user' and 'user_documents' to catch old uploads
                all_documents = await db.admin_select("documents", filters={'entity_id': entity_id} if entity_id else None) or []
                # Filter to only user-related documents
                documents = [doc for doc in all_documents if doc.get('entity_type') in ['user', 'user_documents']]
            elif entity_type == 'property':
                filters['entity_type'] = entity_type
                documents = await db.admin_select("documents", filters=filters if filters else None) or []
            else:
                filters['entity_type'] = entity_type
                documents = await db.admin_select("documents", filters=filters if filters else None) or []
        else:
            # No entity_type filter, fetch all
            documents = await db.admin_select("documents", filters=filters if filters else None) or []
        
        print(f"[ADMIN] Found {len(documents)} documents")
        
        # Add the full public URL to each document
        for doc in documents:
            file_path = doc.get("file_path")
            entity_type = doc.get("entity_type", "")
            
            if file_path:
                try:
                    # Check if file_path is already a full URL (starts with http)
                    if file_path.startswith('http://') or file_path.startswith('https://'):
                        # It's already a full URL, use it directly
                        doc['public_url'] = file_path
                    else:
                        # Determine the correct bucket based on entity_type
                        # Property images go to 'property-images', user documents go to 'documents'
                        bucket_name = "property-images" if entity_type == "property" else "documents"
                        
                        # It's just a path, generate the public URL from the correct bucket
                        try:
                            public_url = db.supabase_client.storage.from_(bucket_name).get_public_url(file_path)
                            doc['public_url'] = public_url
                        except Exception as bucket_error:
                            # Fallback: try documents bucket if property-images fails
                            if bucket_name == "property-images":
                                try:
                                    public_url = db.supabase_client.storage.from_("documents").get_public_url(file_path)
                                    doc['public_url'] = public_url
                                except:
                                    # Last resort: use file_path as-is if it looks like a URL
                                    doc['public_url'] = file_path if '/' in file_path else None
                            else:
                                doc['public_url'] = None
                            print(f"Warning: Using fallback bucket for {file_path}: {bucket_error}")
                except Exception as e:
                    print(f"Error generating public url for {file_path}: {e}")
                    doc['public_url'] = file_path if file_path.startswith('http') else None

        return documents
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error fetching documents: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/upload")
async def admin_upload_document(
    request: Request, _=Depends(require_admin_or_api_key),
    file: UploadFile = File(...),
    entity_id: str = Form(...),
    entity_type: str = Form("user_documents"),
    document_category: str = Form("admin_upload")
):
    """Admin endpoint to upload a document on behalf of a user"""
    try:
        from ..routes.uploads import upload_file_to_storage
        
        # Check if user (entity_id) exists
        user_data = await db.select("users", filters={"id": entity_id})
        if not user_data:
            raise HTTPException(status_code=404, detail=f"User with id {entity_id} not found.")

        # Use entity_id as uploaded_by since admin uploads should be tracked as the user's own documents
        result = await upload_file_to_storage(
            file=file,
            entity_id=entity_id,
            entity_type=entity_type,
            document_category=document_category,
            uploaded_by=entity_id  # Changed from "admin" to entity_id (valid UUID)
        )
        
        return {
            "success": True,
            "message": "Document uploaded successfully by admin.",
            "document": result
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error uploading document: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to upload document: {str(e)}")


# Agent-specific routes
@router.get("/agents/{agent_id}/profile")
async def get_agent_profile(agent_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Get agent profile with documents and application info"""
    try:
        # Get agent user data
        user_data = await db.select("users", filters={"id": agent_id})
        if not user_data:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent = user_data[0]
        
        # Get agent documents if any
        documents = await db.select("documents", filters={"user_id": agent_id}) or []
        
        # Get role requests if any
        role_requests = await db.select("role_requests", filters={"user_id": agent_id}) or []
        
        # Get property assignments
        assigned_properties = await db.select("properties", filters={"agent_id": agent_id}) or []
        
        profile = {
            "agent": agent,
            "documents": documents,
            "roleRequests": role_requests,
            "applicationDate": agent.get("created_at"),
            "lastUpdated": agent.get("updated_at") or agent.get("created_at"),
            "status": agent.get("status"),
            "verificationStatus": agent.get("verification_status"),
            "licenseNumber": agent.get("license_number"),
            "customId": agent.get("custom_id"),
            "assignedProperties": len(assigned_properties)
        }
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting agent profile {agent_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/agents/{agent_id}/approve")
async def approve_agent(agent_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Approve an agent and ensure license number is set"""
    try:
        payload = await request.json() if request else {}
        approval_notes = payload.get("approval_notes", "Agent approved by admin")
        
        # Get user data first
        user_data = await db.select("users", filters={"id": agent_id})
        if not user_data:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        user = user_data[0]
        
        # Get or generate license number
        license_number = user.get('agent_license_number') or user.get('license_number') or user.get('custom_id')
        if not license_number:
            # Generate new license number
            try:
                from ..services.admin_service import generate_custom_id
                license_number = await generate_custom_id('agent')
                print(f"[ADMIN] Generated new license number: {license_number}")
            except Exception as gen_error:
                print(f"[ADMIN] Failed to generate license number: {gen_error}")
                # Fallback to simple format
                import time
                license_number = f"AGT{int(time.time())%1000000:06d}"
            
            print(f"[ADMIN] Generated license number for agent {agent_id}: {license_number}")
        else:
            print(f"[ADMIN] Using existing license number for agent {agent_id}: {license_number}")
        
        update_data = {
            "verification_status": "verified",
            "status": "active",  # Ensure status is 'active' not 'pending'
            "agent_license_number": license_number,
            "license_number": license_number,  # Set both fields for compatibility
            "custom_id": license_number,  # Also update custom_id
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("users", update_data, {"id": agent_id})

        # Send comprehensive approval email
        try:
            updated_user_data = await db.select("users", filters={"id": agent_id})
            if updated_user_data:
                updated_user = updated_user_data[0]
                final_license = updated_user.get('agent_license_number') or updated_user.get('license_number') or license_number
                agent_email = updated_user.get('email')
                agent_name = f"{updated_user.get('first_name', '')} {updated_user.get('last_name', '')}".strip() or "Agent"
                
                subject = "Your Home & Own Agent Account Has Been Approved"
                html_content = f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                    <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                        <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                            <div style="width: 60px; height: 60px; background-color: white; border-radius: 50%; margin: 0 auto 20px; display: flex; align-items: center; justify-content: center;">
                                <span style="font-size: 30px; color: #10b981;">✓</span>
                            </div>
                            <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Agent Account Approved!</h1>
                        </div>
                        <div style="padding: 40px 30px;">
                            <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Congratulations {agent_name}!</h2>
                            <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                Your agent account on Home & Own has been approved and is now active.
                            </p>
                            {f'<div style="background-color: #d1fae5; border-left: 4px solid #10b981; padding: 16px; margin: 30px 0; border-radius: 4px;"><p style="color: #065f46; font-size: 16px; margin: 0;"><strong>Your License Number:</strong> <span style="font-family: monospace; font-size: 18px;">{final_license}</span></p></div>' if final_license else ''}
                            {f'<div style="background-color: #f0f9ff; border-left: 4px solid #2563eb; padding: 16px; margin: 30px 0; border-radius: 4px;"><p style="color: #1e293b; font-size: 14px; margin: 0;"><strong>Admin Notes:</strong> {approval_notes}</p></div>' if approval_notes else ''}
                            <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 30px 0 20px 0;">
                                You can now log in and access your agent dashboard to start managing properties, inquiries, and bookings.
                            </p>
                            <div style="text-align: center; margin: 40px 0;">
                                <a href="https://homeandown.com/agent/login" 
                                   style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                          color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                          font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);">
                                    Login to Agent Dashboard
                                </a>
                            </div>
                            <div style="background-color: #f8fafc; border-radius: 8px; padding: 20px; margin: 30px 0;">
                                <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0; line-height: 1.6;">
                                    <strong>As an approved agent, you can:</strong>
                                </p>
                                <ul style="color: #64748b; font-size: 14px; margin: 0; padding-left: 20px; line-height: 1.8;">
                                    <li>View and manage assigned properties</li>
                                    <li>Respond to inquiries and bookings</li>
                                    <li>Schedule property viewings</li>
                                    <li>Track your performance and earnings</li>
                                    <li>Update your profile and contact information</li>
                                </ul>
                            </div>
                        </div>
                        <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                            <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                                Welcome to the Home & Own agent team!<br>
                                <strong>The Home & Own Team</strong>
                            </p>
                        </div>
                    </div>
                </body>
                </html>
                """
                email_result = await send_email(to=agent_email, subject=subject, html=html_content)
                if email_result.get("status") == "sent":
                    print(f"[ADMIN] ✅ Sent comprehensive agent approval email to: {agent_email}")
                else:
                    print(f"[ADMIN] ⚠️ Failed to send agent approval email: {email_result.get('error', 'Unknown error')}")
                    print(f"[ADMIN] Email result: {email_result}")
        except Exception as email_error:
            print(f"[ADMIN] Exception sending agent approval email: {email_error}")
            import traceback
            print(traceback.format_exc())

        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error approving agent {agent_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/agents/{agent_id}/reject")
async def reject_agent(agent_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Reject an agent"""
    try:
        payload = await request.json() if request else {}
        rejection_reason = payload.get("rejection_reason", "Rejected by admin")
        
        update_data = {
            "verification_status": "rejected",
            "status": "inactive",
            "rejection_reason": rejection_reason,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("users", update_data, {"id": agent_id})
        
        # Send rejection email
        try:
            user_data = await db.select("users", filters={"id": agent_id})
            if user_data:
                user = user_data[0]
                subject = "An update on your Home & Own agent application"
                html_content = f"<p>Hi {user.get('first_name')},</p><p>Thank you for your application to Home & Own as an agent. After careful review, we regret to inform you that your application has been rejected.</p><p><strong>Reason:</strong> {rejection_reason}</p>"
                await send_email(to=user.get('email'), subject=subject, html=html_content)
        except Exception as email_error:
            print(f"[ADMIN] Failed to send agent rejection email: {email_error}")
        
        return result
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error rejecting agent {agent_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/agents/earnings")
async def get_agent_earnings(request: Request, _=Depends(require_admin_or_api_key)):
    """Get agent earnings summary"""
    try:
        # Get all agents
        agents = await db.select("users", filters={"user_type": "agent"}) or []
        
        # Get all commissions
        commissions = await db.select("commissions") or []
        
        # Calculate earnings for each agent
        earnings = []
        for agent in agents:
            agent_commissions = [c for c in commissions if c.get('agent_id') == agent['id']]
            total_earnings = sum(c.get('amount', 0) for c in agent_commissions)
            pending = sum(c.get('amount', 0) for c in agent_commissions if c.get('status') == 'pending')
            paid = sum(c.get('amount', 0) for c in agent_commissions if c.get('status') == 'paid')
            
            earnings.append({
                "agent_id": agent['id'],
                "agent_name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip(),
                "email": agent.get('email'),
                "total_earnings": total_earnings,
                "pending": pending,
                "paid": paid,
                "commission_count": len(agent_commissions)
            })
        
        return earnings
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting agent earnings: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/agents/commissions")
async def get_agent_commissions(request: Request, _=Depends(require_admin_or_api_key)):
    """Get all agent commissions"""
    try:
        commissions = await db.select("commissions") or []
        users = await db.select("users") or []
        
        # Build user map
        user_map = {user['id']: f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() for user in users}
        
        # Add agent names to commissions
        for commission in commissions:
            agent_id = commission.get('agent_id')
            commission['agent_name'] = user_map.get(agent_id, 'Unknown') if agent_id else 'Unassigned'
        
        return commissions
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting agent commissions: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/agents/{agent_id}/commissions")
async def get_agent_commissions_detail(agent_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Get commissions for a specific agent"""
    try:
        commissions = await db.select("commissions", filters={"agent_id": agent_id}) or []
        return commissions
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting agent commissions {agent_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/agents/{agent_id}/commission/set-rate")
async def set_agent_commission_rate(agent_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Set commission rate for an agent"""
    try:
        payload = await request.json()
        commission_rate = payload.get("commission_rate")
        
        if commission_rate is None:
            raise HTTPException(status_code=400, detail="commission_rate is required")
        
        # Update agent's commission rate
        update_data = {
            "commission_rate": commission_rate,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("users", update_data, {"id": agent_id})
        
        return {"success": True, "commission_rate": commission_rate, "agent_id": agent_id}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error setting commission rate for agent {agent_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.post("/bookings/{booking_id}/commission/pay")
async def pay_commission(booking_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Mark a commission as paid for a booking"""
    try:
        payload = await request.json() if request else {}
        
        # Update commission status
        update_data = {
            "status": "paid",
            "paid_at": dt.datetime.utcnow().isoformat(),
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        # Find commission by booking_id
        filters = {"booking_id": booking_id}
        result = await db.update("commissions", update_data, filters)
        
        return {"success": True, "message": "Commission marked as paid", "booking_id": booking_id}
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error paying commission for booking {booking_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/commissions/summary")
async def get_commissions_summary(request: Request, _=Depends(require_admin_or_api_key)):
    """Get commission summary statistics"""
    try:
        # Get all bookings with commissions
        bookings = await db.select("bookings") or []
        
        # Calculate summary statistics
        total_commissions = 0
        pending_commissions = 0
        paid_commissions = 0
        total_bookings = len(bookings)
        
        # Calculate from bookings
        for booking in bookings:
            commission_amount = booking.get('commission_amount', 0) or 0
            commission_status = booking.get('commission_status', 'pending')
            
            if commission_amount > 0:
                total_commissions += commission_amount
                if commission_status == 'paid':
                    paid_commissions += commission_amount
                else:
                    pending_commissions += commission_amount
        
        # Get commission payments if table exists
        try:
            commission_payments = await db.select("commission_payments") or []
            total_payments = len(commission_payments)
        except:
            total_payments = 0
        
        summary = {
            "total_commissions": total_commissions,
            "pending_commissions": pending_commissions,
            "paid_commissions": paid_commissions,
            "total_bookings": total_bookings,
            "total_payments": total_payments,
            "average_commission": total_commissions / total_bookings if total_bookings > 0 else 0
        }
        
        return {"success": True, "summary": summary}
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting commission summary: {e}")
        print(traceback.format_exc())
        # Return empty summary on error
        return {
            "success": True,
            "summary": {
                "total_commissions": 0,
                "pending_commissions": 0,
                "paid_commissions": 0,
                "total_bookings": 0,
                "total_payments": 0,
                "average_commission": 0
            }
        }

@router.get("/commission-payments")
async def get_commission_payments(request: Request, _=Depends(require_admin_or_api_key)):
    """Get all commission payments"""
    try:
        # Try to get from commission_payments table
        try:
            payments = await db.select("commission_payments") or []
            
            # Enhance with agent and booking details
            if payments:
                users = await db.select("users") or []
                bookings = await db.select("bookings") or []
                
                user_map = {u['id']: f"{u.get('first_name', '')} {u.get('last_name', '')}".strip() for u in users}
                booking_map = {b['id']: b for b in bookings}
                
                for payment in payments:
                    agent_id = payment.get('agent_id')
                    booking_id = payment.get('booking_id')
                    
                    payment['agent_name'] = user_map.get(agent_id, 'Unknown') if agent_id else 'Unknown'
                    if booking_id and booking_id in booking_map:
                        booking = booking_map[booking_id]
                        payment['property_id'] = booking.get('property_id')
                        payment['booking_date'] = booking.get('booking_date')
            
            return {"success": True, "payments": payments}
        except Exception as e:
            print(f"[ADMIN] commission_payments table may not exist: {e}")
            # Return empty list if table doesn't exist
            return {"success": True, "payments": []}
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting commission payments: {e}")
        print(traceback.format_exc())
        # Return empty list on error
        return {"success": True, "payments": []}

@router.post("/inquiries/{inquiry_id}/agent-response")
async def agent_response_to_inquiry(inquiry_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Add agent response to an inquiry"""
    try:
        payload = await request.json()
        response_text = payload.get("response")
        agent_id = payload.get("agent_id")
        
        if not response_text:
            raise HTTPException(status_code=400, detail="response is required")
        
        # Update inquiry with agent response
        update_data = {
            "agent_response": response_text,
            "agent_id": agent_id,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("inquiries", update_data, {"id": inquiry_id})
        
        return {"success": True, "message": "Agent response added", "inquiry_id": inquiry_id}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error adding agent response to inquiry {inquiry_id}: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@router.get("/analytics")
async def get_analytics(request: Request, _=Depends(require_admin_or_api_key), range: str = "7d"):
    """Get analytics data"""
    try:
        # Parse range
        range_map = {
            "1d": 1,
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365
        }
        days = range_map.get(range, 7)
        
        # Calculate date range
        end_date = dt.datetime.utcnow()
        start_date = end_date - dt.timedelta(days=days)
        
        # Get statistics
        users = await db.admin_select("users")
        properties = await db.admin_select("properties")
        bookings = await db.admin_select("bookings")
        inquiries = await db.admin_select("inquiries")
        
        # Filter data by date range
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        filtered_users = [u for u in users if u.get('created_at', '') >= start_str and u.get('created_at', '') <= end_str] if users else []
        filtered_properties = [p for p in properties if p.get('created_at', '') >= start_str and p.get('created_at', '') <= end_str] if properties else []
        filtered_bookings = [b for b in bookings if b.get('created_at', '') >= start_str and b.get('created_at', '') <= end_str] if bookings else []
        filtered_inquiries = [i for i in inquiries if i.get('created_at', '') >= start_str and i.get('created_at', '') <= end_str] if inquiries else []
        
        analytics = {
            "range": range,
            "start_date": start_str,
            "end_date": end_str,
            "total_users": len(users) if users else 0,
            "new_users": len(filtered_users),
            "total_properties": len(properties) if properties else 0,
            "new_properties": len(filtered_properties),
            "total_bookings": len(bookings) if bookings else 0,
            "new_bookings": len(filtered_bookings),
            "total_inquiries": len(inquiries) if inquiries else 0,
            "new_inquiries": len(filtered_inquiries),
        }
        
        return analytics
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting analytics: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

# Additional missing routes
@router.post("/users/{user_id}/profile")
async def update_user_profile(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Update user profile data"""
    try:
        payload = await request.json()
        payload["updated_at"] = dt.datetime.utcnow().isoformat()
        return await db.update("users", payload, {"id": user_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/properties/{property_id}/approve-status-change")
async def approve_property_status_change(
    property_id: str,
    payload: dict,
    request: Request,
    _=Depends(require_admin_or_api_key)
):
    """Approve a property status change request from an agent"""
    try:
        notification_id = payload.get("notification_id")
        requested_status = payload.get("requested_status", "").lower()
        
        if not requested_status:
            raise HTTPException(status_code=400, detail="requested_status is required")
        
        # Get property
        properties = await db.select("properties", filters={"id": property_id})
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_data = properties[0]
        
        # Get buyer name from notification metadata if available
        buyer_name = None
        if notification_id:
            try:
                notifications = await db.select("notifications", filters={"id": notification_id}, limit=1)
                if notifications:
                    notification = notifications[0]
                    metadata = notification.get("metadata", {})
                    if isinstance(metadata, str):
                        import json
                        try:
                            metadata = json.loads(metadata)
                        except:
                            metadata = {}
                    buyer_name = metadata.get("buyer_name")
                    print(f"[ADMIN] Found buyer_name in notification metadata: {buyer_name}")
            except Exception as notif_error:
                print(f"[ADMIN] Could not retrieve buyer_name from notification: {notif_error}")
        
        # Also check payload for buyer_name (in case admin provides it)
        if not buyer_name:
            buyer_name = payload.get("buyer_name")
        
        # Update property status
        update_data = {
            "status": requested_status,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        # If status is sold or rented, mark as inactive
        if requested_status in ['sold', 'rented']:
            update_data['verified'] = False  # Remove from active listings
        
        # Store buyer_name in property if available (we'll use a JSON field or store in description/metadata)
        # Since properties table doesn't have buyer_name column, we'll store it in a way that can be retrieved
        # For now, we'll add it to the property's description or create a note
        # TODO: Consider adding buyer_name column to properties table in future migration
        
        # Update property status
        result = await db.update("properties", update_data, {"id": property_id})
        print(f"[ADMIN] Property status update result: {result}")
        print(f"[ADMIN] Updated property {property_id} status to {requested_status}")
        
        # Verify the update was successful
        verify_properties = await db.select("properties", filters={"id": property_id}, limit=1)
        if verify_properties:
            updated_property = verify_properties[0]
            print(f"[ADMIN] Verified property status after update: {updated_property.get('status')}")
            if updated_property.get('status') != requested_status:
                print(f"[ADMIN] WARNING: Property status update may have failed. Expected: {requested_status}, Got: {updated_property.get('status')}")
        
        # If buyer_name is provided and status is sold, update the most recent inquiry for this property
        # This allows the buyer information to be displayed in PropertyDetailsModal
        if requested_status == 'sold' and buyer_name:
            try:
                # Find the most recent inquiry for this property
                inquiries = await db.select("inquiries", filters={"property_id": property_id}, limit=1, order_by="created_at", ascending=False)
                if inquiries:
                    inquiry = inquiries[0]
                    # Update inquiry with buyer name and mark as completed
                    inquiry_update = {
                        "status": "completed",
                        "updated_at": dt.datetime.utcnow().isoformat()
                    }
                    # Store buyer_name in inquiry message or create a note
                    # Since inquiries table doesn't have buyer_name, we'll append it to message
                    current_message = inquiry.get("message", "")
                    if buyer_name not in current_message:
                        inquiry_update["message"] = f"{current_message}\n\n[Property Sold] Buyer: {buyer_name}".strip()
                    await db.update("inquiries", inquiry_update, {"id": inquiry.get("id")})
                    print(f"[ADMIN] Updated inquiry {inquiry.get('id')} with buyer_name: {buyer_name}")
            except Exception as inquiry_error:
                print(f"[ADMIN] Could not update inquiry with buyer_name: {inquiry_error}")
                # Don't fail the approval if inquiry update fails
        
        # Mark notification as read/processed
        if notification_id:
            try:
                await db.update("notifications", {"read": True, "updated_at": dt.datetime.utcnow().isoformat()}, {"id": notification_id})
            except Exception:
                pass  # Notification might not exist, continue anyway
        
        # Send email to agent
        try:
            agent_id = property_data.get("assigned_agent_id") or property_data.get("agent_id")
            if agent_id:
                agents = await db.select("users", filters={"id": agent_id})
                if agents:
                    agent = agents[0]
                    await send_email(
                        agent.get("email"),
                        f"Property Status Change Approved - {property_data.get('title', property_id)}",
                        f"""
                        <p>Hi {agent.get('first_name', 'Agent')},</p>
                        <p>Your request to change the property status to <strong>{requested_status}</strong> has been approved.</p>
                        <p><strong>Property:</strong> {property_data.get('title', property_id)}</p>
                        <p>The property status has been updated successfully.</p>
                        """
                    )
        except Exception as email_error:
            print(f"[ADMIN] Failed to send approval email: {email_error}")
        
        print(f"[ADMIN] Property {property_id} status changed to {requested_status}")
        return {"success": True, "message": f"Property status changed to {requested_status}"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN] Error approving status change: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to approve status change: {str(e)}")

@router.post("/properties/{property_id}/reject-status-change")
async def reject_property_status_change(
    property_id: str,
    payload: dict,
    request: Request,
    _=Depends(require_admin_or_api_key)
):
    """Reject a property status change request from an agent"""
    try:
        notification_id = payload.get("notification_id")
        reason = payload.get("reason", "Status change request rejected by admin")
        
        # Get property
        properties = await db.select("properties", filters={"id": property_id})
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_data = properties[0]
        
        # Mark notification as read/processed
        if notification_id:
            try:
                await db.update("notifications", {
                    "read": True,
                    "updated_at": dt.datetime.utcnow().isoformat(),
                    "metadata": {
                        "rejected": True,
                        "rejection_reason": reason
                    }
                }, {"id": notification_id})
            except Exception:
                pass
        
        # Send email to agent
        try:
            agent_id = property_data.get("assigned_agent_id") or property_data.get("agent_id")
            if agent_id:
                agents = await db.select("users", filters={"id": agent_id})
                if agents:
                    agent = agents[0]
                    await send_email(
                        agent.get("email"),
                        f"Property Status Change Request Rejected - {property_data.get('title', property_id)}",
                        f"""
                        <p>Hi {agent.get('first_name', 'Agent')},</p>
                        <p>Your request to change the property status has been rejected.</p>
                        <p><strong>Property:</strong> {property_data.get('title', property_id)}</p>
                        <p><strong>Reason:</strong> {reason}</p>
                        <p>Please contact admin if you have any questions.</p>
                        """
                    )
        except Exception as email_error:
            print(f"[ADMIN] Failed to send rejection email: {email_error}")
        
        print(f"[ADMIN] Property {property_id} status change request rejected")
        return {"success": True, "message": "Status change request rejected"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN] Error rejecting status change: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reject status change: {str(e)}")

@router.post("/roles/approve")
async def approve_role_request(request: Request, _=Depends(require_admin_or_api_key)):
    """Approve a user's role request"""
    try:
        from ..services.user_role_service import UserRoleService
        import pytz
        
        body = await request.json()
        user_id = body.get("user_id")
        role = body.get("role", "").lower()
        
        if not user_id or not role:
            raise HTTPException(status_code=400, detail="user_id and role are required")
        
        # Get user details
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        
        # Verify and activate the role
        await UserRoleService.verify_role(user_id, role)
        await UserRoleService.activate_role(user_id, role)
        
        # Update user's primary user_type if they're requesting a new primary role
        # Allow users to have multiple roles, but update primary user_type for login purposes
        if role in ['agent', 'seller', 'buyer']:
            await db.update("users", {
                "user_type": role,
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"id": user_id})
            print(f"[ADMIN] Updated user {user_id} primary user_type to {role}")
        
        print(f"[ADMIN] Role '{role}' approved for user: {user_id}")
        
        # Send approval email to user
        try:
            role_display = {
                "buyer": "Buyer",
                "seller": "Seller",
                "agent": "Agent",
                "admin": "Administrator"
            }.get(role, role.title())
            
            email_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                    <div style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); padding: 40px 20px; text-align: center;">
                        <div style="width: 60px; height: 60px; background-color: white; border-radius: 50%; margin: 0 auto 20px; display: flex; align-items: center; justify-content: center;">
                            <span style="font-size: 30px;">✓</span>
                        </div>
                        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Role Request Approved!</h1>
                    </div>
                    
                    <div style="padding: 40px 30px;">
                        <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Congratulations {user.get('first_name', 'User')}!</h2>
                        
                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            Your request for <strong>{role_display}</strong> access has been approved! You now have access to all {role_display.lower()} features.
                        </p>
                        
                        <div style="background-color: #d1fae5; border-left: 4px solid #10b981; padding: 16px; margin: 30px 0; border-radius: 4px;">
                            <p style="color: #065f46; font-size: 14px; margin: 0; line-height: 1.5;">
                                <strong>🎉 What you can do now:</strong><br>
                                • Access {role_display} dashboard and features<br>
                                • Manage your {role_display.lower()} activities<br>
                                • Enjoy full platform capabilities for {role_display.lower()}s
                            </p>
                        </div>
                        
                        <div style="text-align: center; margin: 40px 0;">
                            <a href="{body.get('site_url', 'https://homeandown.com')}/{role}/dashboard" 
                               style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                      color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                      font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3);">
                                Go to {role_display} Dashboard
                            </a>
                        </div>
                        
                        <div style="background-color: #f8fafc; border-radius: 8px; padding: 20px; margin: 30px 0;">
                            <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0; line-height: 1.6;">
                                <strong>Approval Details:</strong>
                            </p>
                            <p style="color: #64748b; font-size: 14px; margin: 0; line-height: 1.6;">
                                • Role: {role_display}<br>
                                • Date: {dt.datetime.now(pytz.UTC).strftime('%B %d, %Y at %I:%M %p UTC')}<br>
                                • Status: Active
                            </p>
                        </div>
                    </div>
                    
                    <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                        <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                            Welcome to the team!<br>
                            <strong>The Home & Own Team</strong>
                        </p>
                        <p style="color: #94a3b8; font-size: 12px; margin: 20px 0 0 0;">
                            © 2025 Home & Own. All rights reserved.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            await send_email(
                to_email=user["email"],
                subject=f"Role Request Approved - Home & Own",
                html_content=email_html
            )
            print(f"[ADMIN] Role approval email sent to: {user['email']}")
        except Exception as email_error:
            print(f"[ADMIN] Failed to send role approval email: {email_error}")
        
        return {
            "success": True,
            "message": f"Role '{role}' approved for user {user_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN] Role approval error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/roles/reject")
async def reject_role_request(request: Request, _=Depends(require_admin_or_api_key)):
    """Reject a user's role request"""
    try:
        from ..services.user_role_service import UserRoleService
        import pytz
        
        body = await request.json()
        user_id = body.get("user_id")
        role = body.get("role", "").lower()
        reason = body.get("reason", "Your role request did not meet our requirements at this time.")
        
        if not user_id or not role:
            raise HTTPException(status_code=400, detail="user_id and role are required")
        
        # Get user details
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        
        # Delete the role request
        await UserRoleService.delete_role(user_id, role)
        
        print(f"[ADMIN] Role '{role}' rejected for user: {user_id}")
        
        # Send rejection email to user
        try:
            role_display = {
                "buyer": "Buyer",
                "seller": "Seller",
                "agent": "Agent",
                "admin": "Administrator"
            }.get(role, role.title())
            
            email_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                    <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 40px 20px; text-align: center;">
                        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Role Request Update</h1>
                    </div>
                    
                    <div style="padding: 40px 30px;">
                        <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user.get('first_name', 'User')},</h2>
                        
                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                            Thank you for your interest in becoming a <strong>{role_display}</strong> on Home & Own. After careful review, we're unable to approve your request at this time.
                        </p>
                        
                        <div style="background-color: #fee2e2; border-left: 4px solid #ef4444; padding: 16px; margin: 30px 0; border-radius: 4px;">
                            <p style="color: #991b1b; font-size: 14px; margin: 0; line-height: 1.5;">
                                <strong>Reason:</strong><br>
                                {reason}
                            </p>
                        </div>
                        
                        <div style="background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 16px; margin: 30px 0; border-radius: 4px;">
                            <p style="color: #1e40af; font-size: 14px; margin: 0; line-height: 1.5;">
                                <strong>💡 Next Steps:</strong><br>
                                • You can reapply after addressing the feedback<br>
                                • Contact support if you have questions: support@homeandown.com<br>
                                • Continue using your current account features
                            </p>
                        </div>
                        
                        <div style="background-color: #f8fafc; border-radius: 8px; padding: 20px; margin: 30px 0;">
                            <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0; line-height: 1.6;">
                                <strong>Request Details:</strong>
                            </p>
                            <p style="color: #64748b; font-size: 14px; margin: 0; line-height: 1.6;">
                                • Requested Role: {role_display}<br>
                                • Date: {dt.datetime.now(pytz.UTC).strftime('%B %d, %Y at %I:%M %p UTC')}<br>
                                • Status: Not Approved
                            </p>
                        </div>
                    </div>
                    
                    <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                        <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                            Thank you for your understanding,<br>
                            <strong>The Home & Own Team</strong>
                        </p>
                        <p style="color: #94a3b8; font-size: 12px; margin: 20px 0 0 0;">
                            © 2025 Home & Own. All rights reserved.
                        </p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            await send_email(
                to_email=user["email"],
                subject=f"Role Request Update - Home & Own",
                html_content=email_html
            )
            print(f"[ADMIN] Role rejection email sent to: {user['email']}")
        except Exception as email_error:
            print(f"[ADMIN] Failed to send role rejection email: {email_error}")
        
        return {
            "success": True,
            "message": f"Role '{role}' rejected for user {user_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN] Role rejection error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/bank")
async def update_user_bank(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Update user bank details"""
    try:
        payload = await request.json()
        update_data = {
            "bank_account_number": payload.get("bank_account_number"),
            "ifsc_code": payload.get("ifsc_code"),
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        return await db.update("users", update_data, {"id": user_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/verify-bank")
async def verify_user_bank(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Verify user bank account"""
    try:
        update_data = {
            "bank_verified": True,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        return await db.update("users", update_data, {"id": user_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/verify-status")
async def update_verification_status(user_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Update user verification status"""
    try:
        payload = await request.json()
        status = payload.get("status")
        update_data = {
            "verification_status": status,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        # When verification_status is set to 'verified', also set email_verified to True
        if status == 'verified':
            update_data['email_verified'] = True
            update_data['email_verified_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
            # Also ensure status is active
            update_data['status'] = 'active'
            print(f"[ADMIN] Setting email_verified=True for user {user_id} via verify-status endpoint")
        elif status == 'rejected':
            # Reset email_verified when rejected
            update_data['email_verified'] = False
            update_data['status'] = 'inactive'
            print(f"[ADMIN] Setting email_verified=False for user {user_id} due to rejection")
        
        return await db.update("users", update_data, {"id": user_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/inquiries/{inquiry_id}/assign-agent")
async def assign_agent_to_inquiry(inquiry_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Assign an agent to an inquiry"""
    try:
        payload = await request.json()
        agent_id = payload.get("agent_id")
        status = payload.get("status", "pending")
        assigned_at = payload.get("assigned_at")
        expires_at = payload.get("expires_at")
        notes = payload.get("notes")
        
        update_data = {
            "agent_id": agent_id,
            "status": status,
            "assigned_at": assigned_at,
            "expires_at": expires_at,
            "notes": notes,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        return await db.update("inquiries", update_data, {"id": inquiry_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/documents/{document_id}/approve")
async def approve_document(document_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Approve a document"""
    try:
        print(f"[ADMIN] Approving document {document_id}")
        update_data = {
            "status": "approved",
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        result = await db.update("documents", update_data, {"id": document_id})
        print(f"[ADMIN] Document approval result: {result}")
        
        # Verify the update worked
        if result and len(result) > 0:
            updated_doc = result[0]
            print(f"[ADMIN] Document {document_id} approved successfully, status: {updated_doc.get('status')}")
            return {"success": True, "document": updated_doc}
        else:
            print(f"[ADMIN] Warning: Document update returned no results")
            # Try to fetch the document to see if it exists
            docs = await db.admin_select("documents", filters={"id": document_id})
            if not docs:
                raise HTTPException(status_code=404, detail="Document not found")
            raise HTTPException(status_code=500, detail="Failed to update document")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error approving document: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to approve document: {str(e)}")

@router.post("/documents/{document_id}/reject")
async def reject_document(document_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Reject a document"""
    try:
        payload = await request.json() if request else {}
        reason = payload.get("reason", "")
        print(f"[ADMIN] Rejecting document {document_id} with reason: {reason}")
        
        # Get document to find the user
        doc_data = await db.select("documents", filters={"id": document_id})
        if not doc_data:
            raise HTTPException(status_code=404, detail="Document not found")
        
        document = doc_data[0]
        user_id = document.get('entity_id')

        update_data = {
            "status": "rejected",
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        if reason:
            update_data["rejection_reason"] = reason
        
        result = await db.update("documents", update_data, {"id": document_id})
        print(f"[ADMIN] Document rejection result: {result}")
        
        # Send rejection email with professional template and resubmit instructions
        if user_id:
            try:
                user_data = await db.select("users", filters={"id": user_id})
                if user_data:
                    user = user_data[0]
                    user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or "User"
                    document_name = document.get('name', 'your document')
                    document_category = document.get('category', 'document')
                    
                    subject = f"Document Resubmission Required - {document_name}"
                    
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="utf-8">
                        <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    </head>
                    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                        <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                            <!-- Header -->
                            <div style="background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); padding: 40px 20px; text-align: center;">
                                <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Home & Own</h1>
                                <p style="color: rgba(255, 255, 255, 0.9); margin: 10px 0 0 0; font-size: 16px;">Document Resubmission Required</p>
                            </div>
                            
                            <!-- Content -->
                            <div style="padding: 40px 30px;">
                                <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {user_name},</h2>
                                
                                <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                    We have reviewed your submitted document <strong>"{document_name}"</strong> and unfortunately, it has been rejected.
                                </p>
                                
                                <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 20px; margin: 25px 0; border-radius: 4px;">
                                    <h3 style="color: #dc2626; margin: 0 0 10px 0; font-size: 18px;">Rejection Reason:</h3>
                                    <p style="color: #7f1d1d; margin: 0; font-size: 16px; line-height: 1.5;">
                                        {reason or 'No specific reason provided. Please ensure your document meets all requirements.'}
                                    </p>
                                </div>
                                
                                <h3 style="color: #1e293b; margin: 30px 0 15px 0; font-size: 20px;">Next Steps:</h3>
                                <ol style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 25px 0; padding-left: 20px;">
                                    <li style="margin-bottom: 10px;">Review the rejection reason above carefully</li>
                                    <li style="margin-bottom: 10px;">Prepare a new document that addresses the issues mentioned</li>
                                    <li style="margin-bottom: 10px;">Log in to your Home & Own account</li>
                                    <li style="margin-bottom: 10px;">Navigate to your profile/documents section</li>
                                    <li style="margin-bottom: 10px;">Upload the corrected document</li>
                                </ol>
                                
                                <!-- Action Buttons -->
                                <div style="text-align: center; margin: 40px 0;">
                                    <a href="https://homeandown.com/login" 
                                       style="display: inline-block; background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); 
                                              color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                              font-weight: 600; font-size: 16px; box-shadow: 0 4px 6px rgba(37, 99, 235, 0.3); margin-right: 15px;">
                                        Login to Resubmit
                                    </a>
                                    <a href="mailto:support@homeandown.com?subject=Document Rejection Query - {document_name}&body=Hi, I need help with my rejected document: {document_name}. Rejection reason: {reason or 'Not specified'}" 
                                       style="display: inline-block; background: #6b7280; 
                                              color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; 
                                              font-weight: 600; font-size: 16px;">
                                        Contact Support
                                    </a>
                                </div>
                                
                                <div style="background-color: #f0f9ff; border-left: 4px solid #0ea5e9; padding: 20px; margin: 25px 0; border-radius: 4px;">
                                    <p style="color: #0c4a6e; margin: 0; font-size: 14px; line-height: 1.5;">
                                        <strong>Need Help?</strong> You can reply directly to this email or contact our support team at 
                                        <a href="mailto:support@homeandown.com" style="color: #0ea5e9;">support@homeandown.com</a>
                                    </p>
                                </div>
                                
                                <p style="color: #64748b; font-size: 14px; line-height: 1.6; margin: 30px 0 0 0;">
                                    Thank you for your patience. We're here to help you complete your verification process successfully.
                                </p>
                            </div>
                            
                            <!-- Footer -->
                            <div style="background-color: #f8fafc; padding: 30px; border-top: 1px solid #e2e8f0; text-align: center;">
                                <p style="color: #64748b; font-size: 14px; margin: 0 0 10px 0;">
                                    Best regards,<br>
                                    <strong>The Home & Own Team</strong>
                                </p>
                                <p style="color: #94a3b8; font-size: 12px; margin: 20px 0 0 0;">
                                    © 2025 Home & Own. All rights reserved.<br>
                                    This is an automated email, but you can reply for support.
                                </p>
                            </div>
                        </div>
                    </body>
                    </html>
                    """
                    
                    email_result = await send_email(to=user.get('email'), subject=subject, html=html_content)
                    if email_result.get("status") == "sent":
                        print(f"[ADMIN] ✅ Sent document rejection email to {user.get('email')} via {email_result.get('provider', 'unknown')}")
                    else:
                        print(f"[ADMIN] ⚠️ Failed to send document rejection email to {user.get('email')}: {email_result.get('error', 'Unknown error')}")
            except Exception as email_error:
                print(f"[ADMIN] ❌ Failed to send document rejection email: {email_error}")
                import traceback
                print(traceback.format_exc())

        # Verify the update worked
        if result and len(result) > 0:
            updated_doc = result[0]
            print(f"[ADMIN] Document {document_id} rejected successfully, status: {updated_doc.get('status')}")
            return {"success": True, "document": updated_doc}
        else:
            print(f"[ADMIN] Warning: Document update returned no results")
            # Try to fetch the document to see if it exists
            docs = await db.admin_select("documents", filters={"id": document_id})
            if not docs:
                raise HTTPException(status_code=404, detail="Document not found")
            raise HTTPException(status_code=500, detail="Failed to update document")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error rejecting document: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to reject document: {str(e)}")

@router.get("/notifications")
async def get_notifications(request: Request, _=Depends(require_admin_or_api_key), user_id: str = None, limit: int = 50):
    """Get notifications for a user - optimized with timeout and limit"""
    try:
        import asyncio
        import time
        from ..core.cache import cache
        
        start_time = time.time()
        
        # Check cache first (30 second cache) - but skip cache for status change requests to ensure fresh data
        cache_key = f"admin_notifications:{user_id or 'all'}:{limit}"
        # Skip cache for admin notifications to ensure status change requests appear immediately
        # cached_result = cache.get(cache_key)
        # if cached_result is not None:
        #     elapsed = (time.time() - start_time) * 1000
        #     print(f"[ADMIN] Notifications cache hit ({elapsed:.0f}ms)")
        #     return cached_result
        
        # For admin, fetch all notifications including those with user_id=None (admin notifications)
        # If user_id is provided, filter by that user_id, otherwise get all notifications
        if user_id:
            filters = {"user_id": user_id}
        else:
            # For admin, we want to see all notifications including admin notifications (user_id=None)
            # Empty filter should get all notifications, but we'll also explicitly fetch None ones
            filters = {}  # Empty filter to get all notifications
        
        # Add timeout to prevent hanging
        try:
            # Fetch all notifications (including those with user_id=None)
            notifications = await asyncio.wait_for(
                db.select("notifications", filters=filters, limit=min(limit, 500), order_by="created_at", ascending=False),
                    timeout=3.0  # Increased timeout for more notifications
            )
            
            # If no user_id filter, ensure we include admin notifications (user_id=None)
            # Filter to include both user-specific and admin notifications (user_id is None)
            if not user_id and notifications:
                # Filter to include notifications where user_id is None or has a value
                # The database should already return all, but let's ensure we're getting them
                all_notifications = notifications
                admin_notifications = [n for n in all_notifications if n.get("user_id") is None]
                user_notifications = [n for n in all_notifications if n.get("user_id") is not None]
                print(f"[ADMIN] Fetched {len(all_notifications)} total notifications")
                print(f"[ADMIN] - Admin notifications (user_id=None): {len(admin_notifications)}")
                print(f"[ADMIN] - User notifications: {len(user_notifications)}")
                print(f"[ADMIN] - Property status requests: {len([n for n in all_notifications if n.get('type') == 'property_status_request'])}")
        except asyncio.TimeoutError:
            print(f"[ADMIN] Notifications query timeout")
            # Return cached result if available, otherwise empty
            if cached_result is not None:
                return cached_result
            return []
        
        result = notifications or []
        
        # Cache result for 30 seconds
        cache.set(cache_key, result, ttl=60)  # Longer cache for faster repeated requests
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[ADMIN] Notifications fetched ({elapsed:.0f}ms, {len(result)} notifications)")
        
        return result
    except Exception as e:
        print(f"[ADMIN] Notifications error: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/property-assignments/{property_id}/tracking")
async def get_property_assignment_tracking(property_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Get complete tracking information for a property's agent assignment process"""
    try:
        from ..services.sequential_agent_notification import SequentialAgentNotificationService
        
        tracking = await SequentialAgentNotificationService.get_assignment_tracking(property_id)
        
        if not tracking or tracking.get("error"):
            raise HTTPException(
                status_code=404,
                detail=tracking.get("error", "Tracking information not found")
            )
        
        return tracking
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting assignment tracking: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/property-assignments/queue")
async def get_all_assignment_queues(request: Request, _=Depends(require_admin_or_api_key), status: Optional[str] = None):
    """Get all property assignment queues (for admin dashboard)"""
    try:
        filters = {}
        if status:
            filters["status"] = status
        
        queues = await db.admin_select("property_assignment_queue", filters=filters) or []
        
        # Enrich with property and agent details
        enriched_queues = []
        for queue in queues:
            property_id = queue.get("property_id")
            property_data = None
            if property_id:
                properties = await db.select("properties", filters={"id": property_id})
                property_data = properties[0] if properties else None
            
            current_agent_id = queue.get("current_agent_id")
            current_agent_data = None
            if current_agent_id:
                agents = await db.select("users", filters={"id": current_agent_id})
                current_agent_data = agents[0] if agents else None
            
            final_agent_id = queue.get("final_agent_id")
            final_agent_data = None
            if final_agent_id:
                agents = await db.select("users", filters={"id": final_agent_id})
                final_agent_data = agents[0] if agents else None
            
            enriched_queues.append({
                **queue,
                "property": property_data,
                "current_agent": current_agent_data,
                "final_agent": final_agent_data
            })
        
        return enriched_queues
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting assignment queues: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/property-assignments/unassigned")
async def get_unassigned_properties(request: Request, _=Depends(require_admin_or_api_key)):
    """Get all properties that are unassigned (no agent assigned)"""
    try:
        # Get properties with no agent assigned
        properties = await db.admin_select("properties", filters={
            "agent_id": None
        }) or []
        
        # Also check properties that have expired queues
        expired_queues = await db.admin_select("property_assignment_queue", filters={
            "status": "expired"
        }) or []
        
        expired_property_ids = [q.get("property_id") for q in expired_queues]
        
        # Get properties from expired queues
        expired_properties = []
        for property_id in expired_property_ids:
            props = await db.select("properties", filters={"id": property_id})
            if props:
                expired_properties.append(props[0])
        
        return {
            "unassigned_without_queue": properties,
            "unassigned_expired_queue": expired_properties,
            "total_unassigned": len(properties) + len(expired_properties)
        }
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting unassigned properties: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/properties/{property_id}/comprehensive-stats")
async def get_property_comprehensive_stats(property_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Get comprehensive statistics for a property including inquiries, bookings, agent, views"""
    try:
        # Get property
        properties = await db.select("properties", filters={"id": property_id})
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_data = properties[0]
        
        # Get inquiries
        inquiries = await db.select("inquiries", filters={"property_id": property_id}) or []
        
        # Get bookings
        bookings = await db.select("bookings", filters={"property_id": property_id}) or []
        
        # Get assigned agent
        assigned_agent = None
        agent_id = property_data.get("agent_id") or property_data.get("assigned_agent_id")
        if agent_id:
            agents = await db.select("users", filters={"id": agent_id})
            if agents:
                agent = agents[0]
                assigned_agent = {
                    "id": agent.get("id"),
                    "name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip(),
                    "email": agent.get("email"),
                    "phone": agent.get("phone_number"),
                    "assignments_count": 0,  # Count of properties assigned to this agent
                    "inquiries_count": 0,  # Count of inquiries for this agent's properties
                    "bookings_count": 0  # Count of bookings for this agent's properties
                }
                # Get agent's total assignments
                agent_properties = await db.select("properties", filters={
                    "$or": [{"agent_id": agent_id}, {"assigned_agent_id": agent_id}]
                }) or []
                assigned_agent["assignments_count"] = len(agent_properties)
                
                # Get agent's total inquiries and bookings
                agent_property_ids = [p.get("id") for p in agent_properties]
                if agent_property_ids:
                    agent_inquiries = await db.select("inquiries", filters={
                        "property_id": {"in": agent_property_ids}
                    }) or []
                    agent_bookings = await db.select("bookings", filters={
                        "property_id": {"in": agent_property_ids}
                    }) or []
                    assigned_agent["inquiries_count"] = len(agent_inquiries)
                    assigned_agent["bookings_count"] = len(agent_bookings)
        
        # Get property owner
        owner = None
        owner_id = property_data.get("owner_id") or property_data.get("added_by")
        if owner_id:
            owners = await db.select("users", filters={"id": owner_id})
            if owners:
                owner = {
                    "id": owners[0].get("id"),
                    "name": f"{owners[0].get('first_name', '')} {owners[0].get('last_name', '')}".strip(),
                    "email": owners[0].get("email"),
                    "phone": owners[0].get("phone_number")
                }
        
        # Calculate stats
        stats = {
            "total_inquiries": len(inquiries),
            "new_inquiries": len([i for i in inquiries if i.get("status") == "new"]),
            "responded_inquiries": len([i for i in inquiries if i.get("status") in ["responded", "contacted"]]),
            "total_bookings": len(bookings),
            "pending_bookings": len([b for b in bookings if b.get("status") == "pending"]),
            "confirmed_bookings": len([b for b in bookings if b.get("status") == "confirmed"]),
            "completed_bookings": len([b for b in bookings if b.get("status") == "completed"]),
            "conversion_rate": round((len(bookings) / max(len(inquiries), 1)) * 100, 2),
            "has_assigned_agent": agent_id is not None,
            "assigned_agent": assigned_agent,
            "property_owner": owner,
            "property_status": property_data.get("status"),
            "property_verified": property_data.get("verified"),
            "created_at": property_data.get("created_at"),
            "updated_at": property_data.get("updated_at")
        }
        
        return {
            "success": True,
            "property_id": property_id,
            "property_title": property_data.get("title"),
            "stats": stats,
            "inquiries": inquiries[:10],  # Last 10 inquiries
            "bookings": bookings[:10]  # Last 10 bookings
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ADMIN] Error getting property comprehensive stats: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(notification_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Mark a notification as read"""
    try:
        update_data = {
            "read": True,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        return await db.update("notifications", update_data, {"id": notification_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/properties/{property_id}/retry-assignment")
async def retry_property_assignment(property_id: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Resets and retries the agent assignment process for a property."""
    try:
        print(f"[ADMIN] Retrying agent assignment for property: {property_id}")

        # 1. Clear the agent_id from the property
        await db.update("properties", {"agent_id": None, "assigned_agent_id": None}, {"id": property_id})

        # 2. Delete old notification records for this property
        await db.delete("agent_property_notifications", {"property_id": property_id})

        # 3. Delete old queue record for this property
        await db.delete("property_assignment_queue", {"property_id": property_id})
        
        print(f"[ADMIN] Cleared previous assignment data for property: {property_id}")

        # 4. Restart the assignment queue
        from ..services.sequential_agent_notification import SequentialAgentNotificationService
        result = await SequentialAgentNotificationService.start_property_assignment_queue(property_id)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to restart assignment queue"))

        return {"success": True, "message": "Property assignment retry process has been initiated."}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ADMIN] Error retrying assignment: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
        
@router.get("/debug/agents-by-zipcode/{zipcode}")
async def debug_agents_by_zipcode(zipcode: str, request: Request, _=Depends(require_admin_or_api_key)):
    """Debug endpoint to check which agents match a zipcode"""
    try:
        # Get all verified active agents
        all_agents = await db.select("users", filters={
            "user_type": "agent",
            "status": "active",
            "verification_status": "verified"
        })
        
        print(f"[DEBUG] Total verified active agents: {len(all_agents or [])}")
        
        if not all_agents:
            return {
                "total_agents": 0,
                "matching_agents": [],
                "message": "No verified active agents found in database"
            }
        
        # Check which have zip_code field
        agents_with_zipcode = [a for a in all_agents if a.get("zip_code")]
        print(f"[DEBUG] Agents with zip_code field: {len(agents_with_zipcode)}")
        
        # Find matching agents
        matching_agents = []
        for agent in all_agents:
            agent_zip = agent.get("zip_code")
            if agent_zip and str(agent_zip).strip() == str(zipcode).strip():
                matching_agents.append({
                    "id": agent.get("id"),
                    "name": f"{agent.get('first_name')} {agent.get('last_name')}",
                    "email": agent.get("email"),
                    "zip_code": agent_zip,
                    "city": agent.get("city"),
                    "state": agent.get("state"),
                    "status": agent.get("status"),
                    "verification_status": agent.get("verification_status")
                })
        
        return {
            "search_zipcode": zipcode,
            "total_agents": len(all_agents),
            "agents_with_zipcode": len(agents_with_zipcode),
            "matching_agents_count": len(matching_agents),
            "matching_agents": matching_agents,
            "sample_agent_zipcodes": [a.get("zip_code") for a in all_agents[:5]] if all_agents else []
        }
    except Exception as e:
        print(f"[DEBUG] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/email-config-status")
async def check_email_configuration(request: Request, _=Depends(require_admin_or_api_key)):
    """Check which email providers are configured"""
    import os
    from ..core.config import settings
    
    config_status = {
        "resend": {
            "configured": bool(os.getenv("RESEND_API_KEY")),
            "priority": 1,
            "details": {
                "api_key": "SET" if os.getenv("RESEND_API_KEY") else "MISSING",
                "template_id": "SET" if os.getenv("RESEND_TEMPLATE_ID") else "MISSING",
                "sender": os.getenv("RESEND_SENDER") or "NOT SET"
            }
        },
        "emailjs": {
            "configured": bool(os.getenv("EMAILJS_SERVICE_ID") and os.getenv("EMAILJS_TEMPLATE_ID")),
            "priority": 2,
            "details": {
                "service_id": "SET" if os.getenv("EMAILJS_SERVICE_ID") else "MISSING",
                "template_id": "SET" if os.getenv("EMAILJS_TEMPLATE_ID") else "MISSING",
                "user_id": "SET" if os.getenv("EMAILJS_USER_ID") else "MISSING"
            }
        },
        "sendgrid": {
            "configured": bool(os.getenv("SENDGRID_API_KEY")),
            "priority": 3,
            "details": {
                "api_key": "SET" if os.getenv("SENDGRID_API_KEY") else "MISSING"
            }
        },
        "gmail_smtp": {
            "configured": bool(settings.GMAIL_USERNAME and settings.GMAIL_APP_PASSWORD),
            "priority": 4,
            "details": {
                "username": settings.GMAIL_USERNAME[:20] + "..." if settings.GMAIL_USERNAME else "MISSING",
                "app_password": "SET" if settings.GMAIL_APP_PASSWORD else "MISSING"
            }
        }
    }
    
    # Determine which provider will be used
    active_provider = None
    for provider, status in config_status.items():
        if status["configured"]:
            active_provider = provider
            break
    
    return {
        "active_provider": active_provider or "NONE (Development mode - emails will be logged only)",
        "providers": config_status,
        "recommendation": "Configure Resend (recommended) or Gmail SMTP for production email delivery"
    }

@router.post("/test-email")
async def test_email_service(request: Request, _=Depends(require_admin_or_api_key)):
    """Test endpoint to verify email service is working"""
    try:
        payload = await request.json()
        to_email = payload.get("to_email")
        
        if not to_email:
            raise HTTPException(status_code=400, detail="to_email is required")
        
        from ..services.email import send_email
        
        email_html = """
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #0ca5e9;">Test Email from Home & Own</h2>
            <p>This is a test email to verify the email service is working correctly.</p>
            <p><strong>If you received this email, the email service is functioning properly!</strong></p>
            <div style="background: #f0f9ff; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <p style="margin: 0;"><strong>Test Details:</strong></p>
                <p style="margin: 5px 0;">Timestamp: {timestamp}</p>
                <p style="margin: 5px 0;">Recipient: {to_email}</p>
            </div>
        </div>
        """.format(timestamp=dt.datetime.utcnow().isoformat(), to_email=to_email)
        
        print(f"[TEST_EMAIL] Attempting to send test email to: {to_email}")
        result = await send_email(
            to=to_email,
            subject="Test Email - Home & Own Email Service",
            html=email_html
        )
        print(f"[TEST_EMAIL] Send result: {result}")
        
        return {
            "success": True,
            "message": "Test email sent successfully",
            "to": to_email,
            "result": result,
            "note": "Check Render logs for detailed email provider information"
        }
    except Exception as e:
        print(f"[TEST_EMAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))