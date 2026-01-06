"""
Routes for analytics and tracking features
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional
from ..db.supabase_client import db
from ..core.security import get_current_user_claims
import datetime as dt
import uuid
import traceback

router = APIRouter()

@router.post("/analytics/property-view")
async def record_property_view(request: Request):
    """Record a property view for analytics"""
    try:
        # Get request data
        data = await request.json()
        property_id = data.get("property_id")
        
        if not property_id:
            raise HTTPException(status_code=400, detail="Property ID is required")
        
        # Try to get user ID from claims (optional - can be anonymous)
        user_id = None
        try:
            claims = get_current_user_claims(request)
            if claims:
                user_id = claims.get("sub")
        except:
            pass  # Anonymous view
        
        # Get viewer metadata
        viewer_ip = request.client.host if request.client else None
        viewer_user_agent = request.headers.get("user-agent")
        session_id = data.get("session_id")
        
        print(f"[ANALYTICS] Recording view for property {property_id} by user {user_id or 'anonymous'}")
        
        # Try to use the database function
        try:
            result = await db.rpc("record_property_view", {
                "property_id_param": property_id,
                "user_id_param": user_id,
                "viewer_ip_param": viewer_ip,
                "viewer_user_agent_param": viewer_user_agent
            })
            print(f"[ANALYTICS] View recorded via RPC: {result}")
            return {"success": True, "view_id": result}
        except Exception as e:
            # Fallback to direct insert if function not available
            print(f"[ANALYTICS] RPC failed, using direct insert: {e}")
            view_data = {
                "id": str(uuid.uuid4()),
                "property_id": property_id,
                "user_id": user_id,
                "viewer_ip": viewer_ip,
                "viewer_user_agent": viewer_user_agent,
                "session_id": session_id,
                "viewed_at": dt.datetime.utcnow().isoformat(),
                "created_at": dt.datetime.utcnow().isoformat()
            }
            result = await db.insert("property_views", view_data)
            print(f"[ANALYTICS] View recorded: {result}")
            return {"success": True, "view_id": view_data["id"]}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANALYTICS] Record view error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to record view: {str(e)}")

@router.get("/analytics/property-views/{property_id}")
async def get_property_views(
    property_id: str,
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: Optional[int] = Query(100)
):
    """Get view analytics for a property"""
    try:
        # Verify user has permission (owner or admin)
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[ANALYTICS] Fetching views for property {property_id}")
        
        # Check if user owns the property or is admin
        property_data = await db.select("properties", filters={"id": property_id})
        if not property_data:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_info = property_data[0]
        user_data = await db.select("users", filters={"id": user_id})
        user_info = user_data[0] if user_data else {}
        
        # Only owner or admin can view analytics
        if property_info.get("owner_id") != user_id and user_info.get("user_type") != "admin":
            raise HTTPException(status_code=403, detail="Not authorized to view analytics for this property")
        
        # Build filters
        filters = {"property_id": property_id}
        
        # Get views
        views = await db.select("property_views", filters=filters, limit=limit)
        views_list = views or []
        
        # Apply date filters if provided (client-side filtering)
        if start_date or end_date:
            filtered_views = []
            for view in views_list:
                viewed_at = view.get("viewed_at")
                if start_date and viewed_at < start_date:
                    continue
                if end_date and viewed_at > end_date:
                    continue
                filtered_views.append(view)
            views_list = filtered_views
        
        # Calculate statistics
        total_views = len(views_list)
        unique_users = len(set(v.get("user_id") for v in views_list if v.get("user_id")))
        anonymous_views = len([v for v in views_list if not v.get("user_id")])
        
        stats = {
            "property_id": property_id,
            "total_views": total_views,
            "unique_users": unique_users,
            "anonymous_views": anonymous_views,
            "authenticated_views": total_views - anonymous_views,
            "views": views_list
        }
        
        print(f"[ANALYTICS] Found {total_views} views for property {property_id}")
        return {"success": True, "analytics": stats}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANALYTICS] Get views error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch views: {str(e)}")

@router.get("/analytics/property-views-count/{property_id}")
async def get_property_view_count(property_id: str):
    """Get total view count for a property (public endpoint)"""
    try:
        print(f"[ANALYTICS] Getting view count for property {property_id}")
        
        # Try to use the database function
        try:
            count = await db.rpc("get_property_view_count", {
                "property_id_param": property_id
            })
            print(f"[ANALYTICS] View count via RPC: {count}")
            return {"success": True, "property_id": property_id, "view_count": count}
        except Exception as e:
            # Fallback to direct query if function not available
            print(f"[ANALYTICS] RPC failed, using direct query: {e}")
            views = await db.select("property_views", filters={"property_id": property_id})
            count = len(views or [])
            print(f"[ANALYTICS] View count: {count}")
            return {"success": True, "property_id": property_id, "view_count": count}
        
    except Exception as e:
        print(f"[ANALYTICS] Get view count error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get view count: {str(e)}")

@router.get("/analytics/seller-dashboard-stats")
async def get_seller_analytics(request: Request):
    """Get comprehensive analytics for seller dashboard"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[ANALYTICS] Fetching seller analytics for user {user_id}")
        
        # Get seller's properties
        properties = await db.select("properties", filters={"owner_id": user_id})
        properties_list = properties or []
        
        property_ids = [p.get("id") for p in properties_list]
        
        # Get view counts for all properties
        total_views = 0
        property_stats = []
        
        for prop in properties_list:
            prop_id = prop.get("id")
            views = await db.select("property_views", filters={"property_id": prop_id})
            view_count = len(views or [])
            total_views += view_count
            
            property_stats.append({
                "property_id": prop_id,
                "property_title": prop.get("title"),
                "view_count": view_count,
                "status": prop.get("status")
            })
        
        # Get inquiries for seller's properties
        all_inquiries = []
        for prop_id in property_ids:
            inquiries = await db.select("inquiries", filters={"property_id": prop_id})
            all_inquiries.extend(inquiries or [])
        
        # Get bookings for seller's properties
        all_bookings = []
        for prop_id in property_ids:
            bookings = await db.select("bookings", filters={"property_id": prop_id})
            all_bookings.extend(bookings or [])
        
        stats = {
            "total_properties": len(properties_list),
            "active_properties": len([p for p in properties_list if p.get("status") == "active"]),
            "total_views": total_views,
            "total_inquiries": len(all_inquiries),
            "total_bookings": len(all_bookings),
            "property_stats": property_stats
        }
        
        print(f"[ANALYTICS] Seller analytics calculated: {stats}")
        return {"success": True, "analytics": stats}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANALYTICS] Seller analytics error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch analytics: {str(e)}")
