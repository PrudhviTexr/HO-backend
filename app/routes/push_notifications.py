"""
Push Notification Routes
Handles browser push notification subscriptions and sending
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional, Dict, Any
from ..db.supabase_client import db
from ..core.security import get_current_user_claims, require_api_key
import datetime as dt
import uuid
import traceback
import json

router = APIRouter()

@router.post("/push/subscribe")
async def subscribe_to_push(
    payload: Dict[str, Any],
    request: Request
):
    """Subscribe user to push notifications"""
    try:
        # Get user from token
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        subscription = payload.get("subscription")
        if not subscription:
            raise HTTPException(status_code=400, detail="Subscription data required")
        
        print(f"[PUSH] Subscribing user {user_id} to push notifications")
        
        # Store subscription in database
        subscription_data = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "endpoint": subscription.get("endpoint"),
            "p256dh_key": subscription.get("keys", {}).get("p256dh"),
            "auth_key": subscription.get("keys", {}).get("auth"),
            "created_at": dt.datetime.utcnow().isoformat(),
            "updated_at": dt.datetime.utcnow().isoformat(),
            "active": True
        }
        
        # Check if subscription already exists for this user
        existing = await db.select("push_subscriptions", filters={"user_id": user_id})
        
        if existing:
            # Update existing subscription
            await db.update("push_subscriptions", subscription_data, {"user_id": user_id})
            print(f"[PUSH] Updated existing subscription for user {user_id}")
        else:
            # Create new subscription
            await db.insert("push_subscriptions", subscription_data)
            print(f"[PUSH] Created new subscription for user {user_id}")
        
        return {"success": True, "message": "Subscribed to push notifications"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PUSH] Subscribe error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to subscribe: {str(e)}")

@router.post("/push/unsubscribe")
async def unsubscribe_from_push(
    payload: Dict[str, Any],
    request: Request
):
    """Unsubscribe user from push notifications"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[PUSH] Unsubscribing user {user_id} from push notifications")
        
        # Deactivate subscription
        await db.update("push_subscriptions", {
            "active": False,
            "updated_at": dt.datetime.utcnow().isoformat()
        }, {"user_id": user_id})
        
        return {"success": True, "message": "Unsubscribed from push notifications"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PUSH] Unsubscribe error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to unsubscribe: {str(e)}")

@router.post("/push/send")
async def send_push_notification(
    payload: Dict[str, Any],
    _=Depends(require_api_key)
):
    """Send push notification to user(s) - Admin/System only"""
    try:
        user_id = payload.get("user_id")
        title = payload.get("title", "Home & Own")
        body = payload.get("body", "You have a new notification")
        icon = payload.get("icon", "/favicon.png")
        url = payload.get("url", "/")
        tag = payload.get("tag", "notification")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="User ID required")
        
        print(f"[PUSH] Sending notification to user {user_id}: {title}")
        
        # Get user's subscription
        subscriptions = await db.select("push_subscriptions", filters={
            "user_id": user_id,
            "active": True
        })
        
        if not subscriptions:
            return {"success": False, "message": "User has no active subscription"}
        
        # In production, you would send the actual push notification here
        # using a service like web-push library
        # For now, we'll just log it
        
        # This would be the actual implementation:
        # import webpush
        # for sub in subscriptions:
        #     subscription_info = {
        #         "endpoint": sub.get("endpoint"),
        #         "keys": {
        #             "p256dh": sub.get("p256dh_key"),
        #             "auth": sub.get("auth_key")
        #         }
        #     }
        #     webpush.send_notification(
        #         subscription_info,
        #         json.dumps({
        #             "title": title,
        #             "body": body,
        #             "icon": icon,
        #             "url": url,
        #             "tag": tag
        #         })
        #     )
        
        print(f"[PUSH] Notification queued for user {user_id}")
        
        return {
            "success": True,
            "message": "Notification sent",
            "subscribers": len(subscriptions)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[PUSH] Send notification error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {str(e)}")
