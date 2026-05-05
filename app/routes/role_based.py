"""
Unified Role-Based API Routes
Routes that automatically determine user role and return appropriate data
"""
from fastapi import APIRouter, HTTPException, Query, Request
from typing import Optional, List, Dict, Any
from ..db.supabase_client import db
from ..core.security import get_current_user_claims
import traceback

router = APIRouter()

@router.get("/bookings")
async def get_role_based_bookings(
    request: Request,
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(1000),
    offset: Optional[int] = Query(0)
):
    """
    Unified endpoint for bookings - automatically routes based on user role
    - Admin: All bookings
    - Agent: Bookings for assigned properties
    - Seller: Bookings for their properties
    - Buyer: Their own bookings
    """
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[ROLE_BASED] [BOOKINGS] Looking up user with ID: {user_id} (type: {type(user_id).__name__})")
        
        # Get user role - try multiple ID formats if needed, with timeout handling
        import asyncio
        try:
            users = await asyncio.wait_for(
                db.select("users", filters={"id": user_id}, limit=1),
                timeout=2.0  # 2 second timeout
            )
        except asyncio.TimeoutError:
            print(f"[ROLE_BASED] [BOOKINGS] Database timeout for user lookup: {user_id}")
            raise HTTPException(status_code=503, detail="Database timeout. Please try again.")
        except Exception as db_error:
            print(f"[ROLE_BASED] [BOOKINGS] Database error: {db_error}")
            raise HTTPException(status_code=503, detail="Database error. Please try again.")
        
        if not users:
            # Try converting to string if it's not already
            if not isinstance(user_id, str):
                user_id_str = str(user_id)
                print(f"[ROLE_BASED] [BOOKINGS] User not found with original ID, trying string conversion: {user_id_str}")
                try:
                    users = await asyncio.wait_for(
                        db.select("users", filters={"id": user_id_str}, limit=1),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    print(f"[ROLE_BASED] [BOOKINGS] Database timeout on retry")
                    raise HTTPException(status_code=503, detail="Database timeout. Please try again.")
            
            if not users:
                # Log more details for debugging
                print(f"[ROLE_BASED] [BOOKINGS] ERROR: User not found in database")
                print(f"[ROLE_BASED] [BOOKINGS] User ID from token: {user_id}")
                print(f"[ROLE_BASED] [BOOKINGS] User ID type: {type(user_id)}")
                print(f"[ROLE_BASED] [BOOKINGS] Claims keys: {list(claims.keys())}")
                # Return 401 (Unauthorized) instead of 404 since this is an authentication issue
                # The user's token is valid but the user doesn't exist - they need to re-login
                raise HTTPException(status_code=401, detail="User account not found. Please log out and log in again.")
        
        user = users[0]
        user_type = user.get("user_type", "").lower()
        
        print(f"[ROLE_BASED] Fetching bookings for user: {user_id}, role: {user_type}")
        
        bookings_list = []
        
        if user_type == "admin":
            # Admin sees all bookings
            filters = {}
            if property_id:
                filters["property_id"] = property_id
            if status:
                filters["status"] = status
            
            bookings_list = await db.select("bookings", filters=filters, limit=limit or 1000, offset=offset, order_by="created_at", ascending=False)
            
        elif user_type == "agent":
            # Agent sees bookings for assigned properties
            print(f"[ROLE_BASED] Fetching bookings for agent: {user_id}")
            
            # Get agent's property IDs from properties table
            try:
                properties = await db.select("properties", filters={
                    "or": [
                        {"agent_id": user_id},
                        {"assigned_agent_id": user_id}
                    ]
                }, limit=1000)
                property_ids = [p.get("id") for p in properties if p.get("id")]
                print(f"[ROLE_BASED] Found {len(property_ids)} properties from properties table")
            except Exception as prop_error:
                print(f"[ROLE_BASED] Error fetching properties: {prop_error}")
                property_ids = []
            
            # Also check assignment tables
            try:
                assignments = await db.select("agent_property_assignments", filters={"agent_id": user_id}, limit=1000)
                assignment_property_ids = [a.get("property_id") for a in assignments if a.get("property_id")]
                property_ids.extend(assignment_property_ids)
                print(f"[ROLE_BASED] Found {len(assignment_property_ids)} properties from agent_property_assignments")
            except Exception as assign_error:
                print(f"[ROLE_BASED] Could not query agent_property_assignments: {assign_error}")
            
            try:
                notifications = await db.select("agent_property_notifications", filters={"agent_id": user_id}, limit=1000)
                notification_property_ids = [n.get("property_id") for n in notifications if n.get("property_id")]
                property_ids.extend(notification_property_ids)
                print(f"[ROLE_BASED] Found {len(notification_property_ids)} properties from agent_property_notifications")
            except Exception as notif_error:
                print(f"[ROLE_BASED] Could not query agent_property_notifications: {notif_error}")
            
            property_ids = list(set(property_ids))
            print(f"[ROLE_BASED] Total unique property IDs: {len(property_ids)}")
            
            # Get bookings by property
            bookings_by_property = []
            if property_ids:
                try:
                    filters = {"property_id": {"in": property_ids}}
                    if status:
                        filters["status"] = status
                    bookings_by_property = await db.select("bookings", filters=filters, limit=limit or 1000, order_by="created_at", ascending=False)
                    print(f"[ROLE_BASED] Found {len(bookings_by_property)} bookings by property")
                except Exception as prop_book_error:
                    print(f"[ROLE_BASED] Error fetching bookings by property: {prop_book_error}")
                    bookings_by_property = []
            
            # Also get bookings directly assigned to agent
            bookings_by_agent = []
            try:
                agent_filters = {"agent_id": user_id}
                if status:
                    agent_filters["status"] = status
                bookings_by_agent = await db.select("bookings", filters=agent_filters, limit=limit or 1000, order_by="created_at", ascending=False)
                print(f"[ROLE_BASED] Found {len(bookings_by_agent)} bookings directly assigned to agent")
            except Exception as agent_book_error:
                print(f"[ROLE_BASED] Error fetching bookings by agent: {agent_book_error}")
                bookings_by_agent = []
            
            # Combine and deduplicate
            all_bookings = (bookings_by_property or []) + (bookings_by_agent or [])
            seen_ids = set()
            bookings_list = []
            for booking in all_bookings:
                booking_id = booking.get("id")
                if booking_id and booking_id not in seen_ids:
                    seen_ids.add(booking_id)
                    bookings_list.append(booking)
            
            print(f"[ROLE_BASED] Total unique bookings after deduplication: {len(bookings_list)}")
            
            # Apply property_id filter if provided
            if property_id:
                bookings_list = [b for b in bookings_list if b.get("property_id") == property_id]
            
        elif user_type == "seller":
            # Seller sees bookings for their properties - fetch from bookings table by property_id
            print(f"[ROLE_BASED] Fetching bookings for seller: {user_id}")
            properties = await db.select("properties", filters={"added_by": user_id}, limit=1000)
            property_ids = [p.get("id") for p in properties if p.get("id")]
            print(f"[ROLE_BASED] Seller owns {len(property_ids)} properties")
            
            if property_ids:
                filters = {"property_id": {"in": property_ids}}
                if property_id:
                    filters["property_id"] = property_id
                if status:
                    filters["status"] = status
                bookings_list = await db.select("bookings", filters=filters, limit=limit or 1000, order_by="created_at", ascending=False)
                print(f"[ROLE_BASED] Found {len(bookings_list)} bookings for seller's properties")
            else:
                bookings_list = []
                print(f"[ROLE_BASED] No properties found for seller, returning empty bookings list")
            
        elif user_type == "buyer":
            # Buyer sees their own bookings - fetch directly from bookings table by user_id
            print(f"[ROLE_BASED] Fetching bookings for buyer: {user_id}")
            filters = {"user_id": user_id}
            if property_id:
                filters["property_id"] = property_id
            if status:
                filters["status"] = status
            bookings_list = await db.select("bookings", filters=filters, limit=limit or 1000, order_by="created_at", ascending=False)
            print(f"[ROLE_BASED] Found {len(bookings_list)} bookings for buyer")
        
        else:
            raise HTTPException(status_code=403, detail=f"Invalid user type: {user_type}")
        
        # Enhance bookings with property and user details
        enhanced_bookings = []
        for booking in bookings_list:
            prop_id = booking.get("property_id")
            user_id_booking = booking.get("user_id")
            
            property_data = None
            user_data = None
            
            if prop_id:
                properties = await db.select("properties", filters={"id": prop_id}, limit=1)
                if properties:
                    property_data = properties[0]
            
            if user_id_booking:
                users = await db.select("users", filters={"id": user_id_booking}, limit=1)
                if users:
                    user_data = users[0]
            
            enhanced_booking = {
                **booking,
                "property": property_data,
                "user": user_data
            }
            enhanced_bookings.append(enhanced_booking)
        
        print(f"[ROLE_BASED] Returning {len(enhanced_bookings)} bookings for {user_type}")
        return {
            "success": True,
            "bookings": enhanced_bookings,
            "total": len(enhanced_bookings)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ROLE_BASED] Get bookings error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch bookings: {str(e)}")

@router.get("/inquiries")
async def get_role_based_inquiries(
    request: Request,
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(1000),
    offset: Optional[int] = Query(0)
):
    """
    Unified endpoint for inquiries - automatically routes based on user role
    - Admin: All inquiries
    - Agent: Inquiries for assigned properties
    - Seller: Inquiries for their properties
    - Buyer: Their own inquiries
    """
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[ROLE_BASED] [INQUIRIES] Looking up user with ID: {user_id} (type: {type(user_id).__name__})")
        
        # Get user role - try multiple ID formats if needed, with timeout handling
        import asyncio
        try:
            users = await asyncio.wait_for(
                db.select("users", filters={"id": user_id}, limit=1),
                timeout=2.0  # 2 second timeout
            )
        except asyncio.TimeoutError:
            print(f"[ROLE_BASED] [INQUIRIES] Database timeout for user lookup: {user_id}")
            raise HTTPException(status_code=503, detail="Database timeout. Please try again.")
        except Exception as db_error:
            print(f"[ROLE_BASED] [INQUIRIES] Database error: {db_error}")
            raise HTTPException(status_code=503, detail="Database error. Please try again.")
        
        if not users:
            # Try converting to string if it's not already
            if not isinstance(user_id, str):
                user_id_str = str(user_id)
                print(f"[ROLE_BASED] [INQUIRIES] User not found with original ID, trying string conversion: {user_id_str}")
                try:
                    users = await asyncio.wait_for(
                        db.select("users", filters={"id": user_id_str}, limit=1),
                        timeout=2.0
                    )
                except asyncio.TimeoutError:
                    print(f"[ROLE_BASED] [INQUIRIES] Database timeout on retry")
                    raise HTTPException(status_code=503, detail="Database timeout. Please try again.")
            
            if not users:
                # Log more details for debugging
                print(f"[ROLE_BASED] [INQUIRIES] ERROR: User not found in database")
                print(f"[ROLE_BASED] [INQUIRIES] User ID from token: {user_id}")
                print(f"[ROLE_BASED] [INQUIRIES] User ID type: {type(user_id)}")
                print(f"[ROLE_BASED] [INQUIRIES] Claims keys: {list(claims.keys())}")
                # Return 401 (Unauthorized) instead of 404 since this is an authentication issue
                # The user's token is valid but the user doesn't exist - they need to re-login
                raise HTTPException(status_code=401, detail="User account not found. Please log out and log in again.")
        
        user = users[0]
        user_type = user.get("user_type", "").lower()
        
        print(f"[ROLE_BASED] Fetching inquiries for user: {user_id}, role: {user_type}")
        
        inquiries_list = []
        
        if user_type == "admin":
            # Admin sees all inquiries
            filters = {}
            if property_id:
                filters["property_id"] = property_id
            if status:
                filters["status"] = status
            
            inquiries_list = await db.select("inquiries", filters=filters, limit=limit or 1000, offset=offset, order_by="created_at", ascending=False)
            
        elif user_type == "agent":
            # Agent sees inquiries for assigned properties
            print(f"[ROLE_BASED] Fetching inquiries for agent: {user_id}")
            
            # Get agent's property IDs from properties table
            try:
                properties = await db.select("properties", filters={
                    "or": [
                        {"agent_id": user_id},
                        {"assigned_agent_id": user_id}
                    ]
                }, limit=1000)
                property_ids = [p.get("id") for p in properties if p.get("id")]
                print(f"[ROLE_BASED] Found {len(property_ids)} properties from properties table")
            except Exception as prop_error:
                print(f"[ROLE_BASED] Error fetching properties: {prop_error}")
                property_ids = []
            
            # Also check assignment tables
            try:
                assignments = await db.select("agent_property_assignments", filters={"agent_id": user_id}, limit=1000)
                assignment_property_ids = [a.get("property_id") for a in assignments if a.get("property_id")]
                property_ids.extend(assignment_property_ids)
                print(f"[ROLE_BASED] Found {len(assignment_property_ids)} properties from agent_property_assignments")
            except Exception as assign_error:
                print(f"[ROLE_BASED] Could not query agent_property_assignments: {assign_error}")
            
            try:
                notifications = await db.select("agent_property_notifications", filters={"agent_id": user_id}, limit=1000)
                notification_property_ids = [n.get("property_id") for n in notifications if n.get("property_id")]
                property_ids.extend(notification_property_ids)
                print(f"[ROLE_BASED] Found {len(notification_property_ids)} properties from agent_property_notifications")
            except Exception as notif_error:
                print(f"[ROLE_BASED] Could not query agent_property_notifications: {notif_error}")
            
            property_ids = list(set(property_ids))
            print(f"[ROLE_BASED] Total unique property IDs: {len(property_ids)}")
            
            # Get inquiries by property - fetch from inquiries table WHERE property_id IN (assigned property_ids)
            # This ensures we get ALL inquiries for assigned properties, even if inquiries.assigned_agent_id is NULL
            inquiries_by_property = []
            if property_ids:
                try:
                    filters = {"property_id": {"in": property_ids}}
                    if status:
                        filters["status"] = status
                    inquiries_by_property = await db.select("inquiries", filters=filters, limit=limit or 1000, order_by="created_at", ascending=False)
                    print(f"[ROLE_BASED] Found {len(inquiries_by_property)} inquiries by property_id (from inquiries table)")
                except Exception as prop_inq_error:
                    print(f"[ROLE_BASED] Error fetching inquiries by property: {prop_inq_error}")
                    inquiries_by_property = []
            
            # Also get inquiries directly assigned to agent (where inquiries.assigned_agent_id = user_id)
            # This catches inquiries that are directly assigned but property might not be in assigned list
            inquiries_by_agent = []
            try:
                agent_filters = {"assigned_agent_id": user_id}
                if status:
                    agent_filters["status"] = status
                inquiries_by_agent = await db.select("inquiries", filters=agent_filters, limit=limit or 1000, order_by="created_at", ascending=False)
                print(f"[ROLE_BASED] Found {len(inquiries_by_agent)} inquiries directly assigned to agent (inquiries.assigned_agent_id)")
            except Exception as agent_inq_error:
                print(f"[ROLE_BASED] Error fetching inquiries by agent: {agent_inq_error}")
                inquiries_by_agent = []
            
            # Also check agent_id field if it exists (for backward compatibility)
            try:
                agent_id_filters = {"agent_id": user_id}
                if status:
                    agent_id_filters["status"] = status
                inquiries_by_agent_id = await db.select("inquiries", filters=agent_id_filters, limit=limit or 1000)
                if inquiries_by_agent_id:
                    print(f"[ROLE_BASED] Found {len(inquiries_by_agent_id)} inquiries by agent_id field")
                    inquiries_by_agent.extend(inquiries_by_agent_id)
            except Exception as agent_id_error:
                print(f"[ROLE_BASED] Note: agent_id field may not exist: {agent_id_error}")
            
            # Combine and deduplicate
            all_inquiries = (inquiries_by_property or []) + (inquiries_by_agent or [])
            seen_ids = set()
            inquiries_list = []
            for inquiry in all_inquiries:
                inquiry_id = inquiry.get("id")
                if inquiry_id and inquiry_id not in seen_ids:
                    seen_ids.add(inquiry_id)
                    inquiries_list.append(inquiry)
            
            print(f"[ROLE_BASED] Total unique inquiries after deduplication: {len(inquiries_list)}")
            
            # Apply property_id filter if provided
            if property_id:
                inquiries_list = [i for i in inquiries_list if i.get("property_id") == property_id]
            
        elif user_type == "seller":
            # Seller sees inquiries for their properties - fetch from inquiries table by property_id
            print(f"[ROLE_BASED] Fetching inquiries for seller: {user_id}")
            properties = await db.select("properties", filters={"added_by": user_id}, limit=1000)
            property_ids = [p.get("id") for p in properties if p.get("id")]
            print(f"[ROLE_BASED] Seller owns {len(property_ids)} properties")
            
            if property_ids:
                filters = {"property_id": {"in": property_ids}}
                if property_id:
                    filters["property_id"] = property_id
                if status:
                    filters["status"] = status
                inquiries_list = await db.select("inquiries", filters=filters, limit=limit or 1000, order_by="created_at", ascending=False)
                print(f"[ROLE_BASED] Found {len(inquiries_list)} inquiries for seller's properties")
            else:
                inquiries_list = []
                print(f"[ROLE_BASED] No properties found for seller, returning empty inquiries list")
            
        elif user_type == "buyer":
            # Buyer sees their own inquiries - fetch directly from inquiries table by user_id
            print(f"[ROLE_BASED] Fetching inquiries for buyer: {user_id}")
            filters = {"user_id": user_id}
            if property_id:
                filters["property_id"] = property_id
            if status:
                filters["status"] = status
            inquiries_list = await db.select("inquiries", filters=filters, limit=limit or 1000, order_by="created_at", ascending=False)
            print(f"[ROLE_BASED] Found {len(inquiries_list)} inquiries for buyer")
        
        else:
            raise HTTPException(status_code=403, detail=f"Invalid user type: {user_type}")
        
        # Enhance inquiries with property and user details
        enhanced_inquiries = []
        for inquiry in inquiries_list:
            prop_id = inquiry.get("property_id")
            user_id_inquiry = inquiry.get("user_id")
            
            property_data = None
            user_data = None
            
            if prop_id:
                properties = await db.select("properties", filters={"id": prop_id}, limit=1)
                if properties:
                    property_data = properties[0]
            
            if user_id_inquiry:
                users = await db.select("users", filters={"id": user_id_inquiry}, limit=1)
                if users:
                    user_data = users[0]
            
            enhanced_inquiry = {
                **inquiry,
                "property": property_data,
                "user": user_data
            }
            enhanced_inquiries.append(enhanced_inquiry)
        
        print(f"[ROLE_BASED] Returning {len(enhanced_inquiries)} inquiries for {user_type}")
        return {
            "success": True,
            "inquiries": enhanced_inquiries,
            "total": len(enhanced_inquiries)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ROLE_BASED] Get inquiries error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch inquiries: {str(e)}")

