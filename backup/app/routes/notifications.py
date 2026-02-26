"""
Notifications Routes

Provides endpoints for managing user notifications.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from pydantic import BaseModel
import logging

from ..db.supabase_client import db
from ..core.auth import get_current_user_optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class MarkAllReadRequest(BaseModel):
    user_id: str | int


@router.get("")
async def list_notifications(
    user_id: Optional[str] = None,
    unread_only: bool = False,
    current_user = Depends(get_current_user_optional)
):
    """
    List notifications for a user
    
    - **user_id**: Optional user ID filter (defaults to current user)
    - **unread_only**: If true, return only unread notifications
    """
    try:
        # Use current_user if user_id not provided
        if not user_id and current_user:
            user_id = str(current_user.get("id"))
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id required")
        
        logger.info(f"Listing notifications for user: {user_id}")
        
        # Build filters
        filters = {"user_id": user_id}
        if unread_only:
            filters["read"] = False
        
        # Query notifications
        notifications = await db.select(
            "notifications",
            filters=filters,
            order_by="created_at.desc",
            limit=100
        )
        
        return {
            "success": True,
            "data": notifications
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{notification_id}/read")
async def mark_as_read(
    notification_id: str,
    current_user = Depends(get_current_user_optional)
):
    """
    Mark a notification as read
    
    - **notification_id**: Notification ID
    """
    try:
        logger.info(f"Marking notification as read: {notification_id}")
        
        # Update notification
        result = await db.update(
            "notifications",
            {"id": notification_id},
            {"read": True}
        )
        
        return {
            "success": True,
            "message": "Notification marked as read",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Error marking notification as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mark-all-read")
async def mark_all_as_read(
    request: MarkAllReadRequest,
    current_user = Depends(get_current_user_optional)
):
    """
    Mark all notifications as read for a user
    
    - **user_id**: User ID
    """
    try:
        logger.info(f"Marking all notifications as read for user: {request.user_id}")
        
        # Get all unread notifications for the user
        unread = await db.select(
            "notifications",
            filters={"user_id": str(request.user_id), "read": False}
        )
        
        # Mark each as read
        for notification in unread:
            await db.update(
                "notifications",
                {"id": notification["id"]},
                {"read": True}
            )
        
        return {
            "success": True,
            "message": f"Marked {len(unread)} notifications as read"
        }
        
    except Exception as e:
        logger.error(f"Error marking all notifications as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))
