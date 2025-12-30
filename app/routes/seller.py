from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional, List, Dict, Any
from ..db.supabase_client import db
from ..core.security import get_current_user_claims
import datetime as dt
import traceback
import uuid

router = APIRouter()

@router.get("/dashboard/stats")
async def get_seller_dashboard_stats(request: Request):
    """Get comprehensive seller dashboard statistics"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[SELLER] Fetching dashboard stats for user: {user_id}")
        
        # Get seller's properties - fetch all properties for accurate stats (no limit to ensure all are counted)
        properties = await db.select("properties", filters={"added_by": user_id}, limit=10000)
        properties_list = properties or []
        
        # Calculate stats
        total_properties = len(properties_list)
        active_properties = len([p for p in properties_list if p.get("status") == "active"])
        pending_properties = len([p for p in properties_list if p.get("status") == "pending"])
        verified_properties = len([p for p in properties_list if p.get("verified") == True])
        
        # Get inquiries for seller's properties
        property_ids = [p.get("id") for p in properties_list]
        total_inquiries = 0
        total_views = 0
        
        if property_ids:
            # Limit queries for dashboard stats (performance optimization)
            inquiries = await db.select("inquiries", filters={"property_id": {"in": property_ids[:50]}}, limit=100)
            total_inquiries = len(inquiries or [])
            
            # Calculate total views (mock for now - will be implemented with analytics)
            total_views = sum(p.get("views_count", 0) for p in properties_list)
        
        # Get bookings for seller's properties
        total_bookings = 0
        if property_ids:
            # Limit queries for dashboard stats (performance optimization)
            bookings = await db.select("bookings", filters={"property_id": {"in": property_ids[:50]}}, limit=100)
            total_bookings = len(bookings or [])
        
        # Calculate earnings (mock calculation)
        monthly_earnings = active_properties * 5000  # Placeholder calculation
        
        # Response rate calculation
        response_rate = 0
        if total_views > 0:
            response_rate = round((total_inquiries / total_views) * 100, 2)
        
        stats = {
            "total_properties": total_properties,
            "active_properties": active_properties,
            "pending_properties": pending_properties,
            "verified_properties": verified_properties,
            "total_views": total_views,
            "total_inquiries": total_inquiries,
            "total_bookings": total_bookings,
            "monthly_earnings": monthly_earnings,
            "response_rate": response_rate,
            "conversion_rate": round((total_bookings / max(total_inquiries, 1)) * 100, 2)
        }
        
        print(f"[SELLER] Dashboard stats calculated: {stats}")
        return {"success": True, "stats": stats}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Dashboard stats error: {e}")
        print(f"[SELLER] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard stats: {str(e)}")

@router.get("/properties")
async def get_seller_properties(
    request: Request,
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get seller's properties with detailed information"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[SELLER] Fetching properties for user: {user_id}")
        
        # Build filters - only show properties added by seller
        filters = {"added_by": user_id}
        if status:
            filters["status"] = status
        
        # Get properties with timeout
        import asyncio
        try:
            properties = await asyncio.wait_for(
                db.select("properties", filters=filters, limit=limit, offset=offset, order_by="created_at", ascending=False),
                    timeout=1.5  # 1.5 second timeout for faster response
            )
        except asyncio.TimeoutError:
            print(f"[SELLER] Properties query timeout for user: {user_id}")
            return {"success": True, "properties": [], "total": 0}
        
        properties_list = properties or []
        
        # Filter out BUY listing type properties - sellers should only see their own properties for sale/rent
        properties_list = [p for p in properties_list if p.get("listing_type") != "BUY"]
        
        # Apply offset manually if needed (for pagination)
        if offset and offset > 0:
            properties_list = properties_list[offset:]
        
        # Batch fetch all related data to avoid N+1 queries (major performance optimization)
        property_ids = [p.get("id") for p in properties_list if p.get("id")]
        
        # Get unique agent IDs
        agent_ids = list(set([p.get("agent_id") or p.get("assigned_agent_id") for p in properties_list if p.get("agent_id") or p.get("assigned_agent_id")]))
        
        # Batch fetch inquiries, bookings, images, and agents in parallel
        import asyncio
        
        # Execute all queries in parallel
        try:
            tasks = []
            if property_ids:
                tasks.append(db.select("inquiries", filters={"property_id": {"in": property_ids}}))
                tasks.append(db.select("bookings", filters={"property_id": {"in": property_ids}}))
                tasks.append(db.select("documents", filters={"entity_type": "property", "entity_id": {"in": property_ids}}))
            else:
                # No properties - return empty lists
                inquiries_all, bookings_all, images_all, agents_all = [], [], [], []
                tasks = []
            
            if tasks:
                if agent_ids:
                    tasks.append(db.select("users", filters={"id": {"in": agent_ids}}, limit=100))
                
                # Add timeout to parallel queries
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=2.0  # 2 second timeout for all parallel queries
                )
                inquiries_all = results[0] if not isinstance(results[0], Exception) else []
                bookings_all = results[1] if not isinstance(results[1], Exception) else []
                images_all = results[2] if not isinstance(results[2], Exception) else []
                agents_all = results[3] if len(results) > 3 and not isinstance(results[3], Exception) else []
            else:
                agents_all = []
        except Exception as batch_error:
            print(f"[SELLER] Batch fetch error: {batch_error}")
            inquiries_all, bookings_all, images_all, agents_all = [], [], [], []
        
        # Group data by property_id for O(1) lookup
        inquiries_by_property = {}
        for inquiry in inquiries_all or []:
            prop_id = inquiry.get("property_id")
            if prop_id:
                if prop_id not in inquiries_by_property:
                    inquiries_by_property[prop_id] = []
                inquiries_by_property[prop_id].append(inquiry)
        
        bookings_by_property = {}
        for booking in bookings_all or []:
            prop_id = booking.get("property_id")
            if prop_id:
                if prop_id not in bookings_by_property:
                    bookings_by_property[prop_id] = []
                bookings_by_property[prop_id].append(booking)
        
        images_by_property = {}
        cover_photos_by_property = {}
        for doc in images_all or []:
            prop_id = doc.get("entity_id")
            file_type = doc.get("file_type", "")
            doc_category = doc.get("document_category", "")
            if prop_id and file_type.startswith("image/"):
                image_url = doc.get("file_path") or doc.get("url")
                if image_url:
                    # If it's not already a full URL, convert file_path to public URL
                    if not (image_url.startswith('http://') or image_url.startswith('https://')):
                        try:
                            # Property images are in 'property-images' bucket
                            public_url = db.supabase_client.storage.from_('property-images').get_public_url(image_url)
                            image_url = public_url
                        except Exception as url_error:
                            print(f"[SELLER] Failed to get public URL for {image_url}: {url_error}")
                            # Try documents bucket as fallback
                            try:
                                public_url = db.supabase_client.storage.from_('documents').get_public_url(image_url)
                                image_url = public_url
                            except:
                                # Use file_path as-is if conversion fails
                                pass
                    
                    # Check if this is a cover photo
                    if doc_category == 'cover_photo':
                        cover_photos_by_property[prop_id] = image_url
                    else:
                        # Regular property image
                        if prop_id not in images_by_property:
                            images_by_property[prop_id] = []
                        images_by_property[prop_id].append(image_url)
        
        agents_by_id = {}
        for agent in agents_all or []:
            agent_id = agent.get("id")
            if agent_id:
                agents_by_id[agent_id] = agent
        
        # Enhance properties with pre-fetched data
        enhanced_properties = []
        for property_data in properties_list:
            property_id = property_data.get("id")
            
            # Get counts from pre-fetched data
            inquiries = inquiries_by_property.get(property_id, [])
            inquiries_count = len(inquiries)
            
            bookings = bookings_by_property.get(property_id, [])
            bookings_count = len(bookings)
            confirmed_bookings_count = len([b for b in bookings if (b.get("status") or "").lower() in ["confirmed", "completed"]])
            
            views_count = property_data.get("views_count", 0)
            
            # Get assigned agent from pre-fetched data
            assigned_agent = None
            agent_id = property_data.get("agent_id") or property_data.get("assigned_agent_id")
            if agent_id and agent_id in agents_by_id:
                agent = agents_by_id[agent_id]
                assigned_agent = {
                    "id": agent.get("id"),
                    "name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip(),
                    "email": agent.get("email"),
                    "phone": agent.get("phone_number"),
                    "assigned_at": property_data.get("assigned_at")
                }
            
            # Get property images from pre-fetched data
            property_images = images_by_property.get(property_id, [])
            cover_image = cover_photos_by_property.get(property_id) or property_data.get("cover_image")
            
            # If cover_image exists, add it to the beginning of images array
            if cover_image and cover_image not in property_images:
                property_images = [cover_image] + property_images
            
            enhanced_property = {
                **property_data,
                "inquiries_count": inquiries_count,
                "bookings_count": bookings_count,
                "confirmed_bookings_count": confirmed_bookings_count,
                "views_count": views_count,
                "last_inquiry_date": inquiries[0].get("created_at") if inquiries else None,
                "last_booking_date": bookings[0].get("created_at") if bookings else None,
                "assigned_agent": assigned_agent,
                "images": property_images,
                "cover_image": cover_image or property_data.get("cover_image")
            }
            
            enhanced_properties.append(enhanced_property)
        
        print(f"[SELLER] Found {len(enhanced_properties)} properties")
        return {"success": True, "properties": enhanced_properties, "total": len(enhanced_properties)}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Get properties error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch properties: {str(e)}")

@router.get("/inquiries")
async def get_seller_inquiries(
    request: Request,
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get inquiries for seller's properties - optimized for speed"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Check cache first (1 minute cache for faster response)
        from ..core.cache import cache
        cache_key = f"seller_inquiries:{user_id}:{property_id or 'all'}:{status or 'all'}:{limit or 20}:{offset or 0}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            return cached_result
        
        # Optimize: Build filters directly without fetching all properties first
        # If property_id is provided, use it directly; otherwise fetch property IDs with minimal limit
        if property_id:
            # Direct property filter
            filters = {"property_id": property_id}
            # Verify the property belongs to this seller (skip if we want faster response)
            # properties = await db.select("properties", filters={"id": property_id, "added_by": user_id}, limit=1)
            # if not properties:
            #     return {"success": True, "inquiries": [], "total": 0}
        else:
            # Get seller's property IDs - increase limit to get all properties for inquiries
            properties = await db.select("properties", filters={"added_by": user_id}, limit=1000)  # Increased to get all properties
            property_ids = [p.get("id") for p in (properties or [])]
            
            if not property_ids:
                result = {"success": True, "inquiries": [], "total": 0}
                cache.set(cache_key, result, ttl=120)  # Cache for 2 minutes for faster repeated requests
                return result
            
            filters = {"property_id": {"in": property_ids}}
        
        if status:
            filters["status"] = status
        
        # Get inquiries with limit and ordering - increase limit to get all inquiries
        inquiries = await db.select("inquiries", filters=filters, limit=min(limit or 1000, 1000), order_by="created_at", ascending=False)
        inquiries_list = inquiries or []
        
        # Early return if no inquiries
        if not inquiries_list:
            result = {"success": True, "inquiries": [], "total": 0}
            cache.set(cache_key, result, ttl=120)  # Cache for 2 minutes for faster repeated requests
            return result
        
        # Apply offset manually if needed (for pagination)
        if offset and offset > 0:
            inquiries_list = inquiries_list[offset:]
        
        # Batch fetch all related data to avoid N+1 queries (performance optimization)
        # Minimal limits for fastest response
        property_ids_from_inquiries = list(set([inq.get("property_id") for inq in inquiries_list if inq.get("property_id")]))[:10]  # Reduced from 20 to 10
        user_ids_from_inquiries = list(set([inq.get("user_id") for inq in inquiries_list if inq.get("user_id")]))[:10]  # Reduced from 20 to 10
        
        # Fetch all properties, agents, and users in parallel with very short timeouts
        import asyncio
        
        try:
            # Execute queries in parallel only if we have IDs to fetch, with very short timeout
            if property_ids_from_inquiries and user_ids_from_inquiries:
                properties_all, users_all = await asyncio.wait_for(
                    asyncio.gather(
                        db.select("properties", filters={"id": {"in": property_ids_from_inquiries}}, limit=10),
                        db.select("users", filters={"id": {"in": user_ids_from_inquiries}}, limit=10),
                        return_exceptions=True
                    ),
                    timeout=2.0  # Reduced from 3 to 2 seconds for faster failure
                )
            elif property_ids_from_inquiries:
                properties_all = await asyncio.wait_for(
                    db.select("properties", filters={"id": {"in": property_ids_from_inquiries}}, limit=10),
                    timeout=2.0
                )
                users_all = []
            elif user_ids_from_inquiries:
                properties_all = []
                users_all = await asyncio.wait_for(
                    db.select("users", filters={"id": {"in": user_ids_from_inquiries}}, limit=10),
                    timeout=2.0
                )
            else:
                properties_all, users_all = [], []
            
            # Handle exceptions - continue with empty data if queries fail
            if isinstance(properties_all, Exception):
                properties_all = []
            if isinstance(users_all, Exception):
                users_all = []
        except asyncio.TimeoutError:
            # Return with empty related data if timeout - inquiries data is still valid
            properties_all, users_all = [], []
        except Exception as batch_error:
            # Continue with empty related data if error
            properties_all, users_all = [], []
        
        # Group by ID for O(1) lookup
        properties_by_id = {p.get("id"): p for p in properties_all if p.get("id")}
        users_by_id = {u.get("id"): u for u in users_all if u.get("id")}
        
        # Get unique agent IDs from properties (limit to prevent too many queries)
        # Skip agent fetching if we're running low on time - this is optional data
        agent_ids = list(set([
            p.get("agent_id") or p.get("assigned_agent_id") 
            for p in properties_all 
            if p.get("agent_id") or p.get("assigned_agent_id")
        ]))[:10]  # Reduced from 20 to 10 agents max
        
        # Fetch agents in parallel with shorter timeout (optional data - can skip if slow)
        agents_all = []
        if agent_ids:
            try:
                agents_all = await asyncio.wait_for(
                    db.select("users", filters={"id": {"in": agent_ids}}, limit=10),
                    timeout=2.0  # Reduced from 3 to 2 seconds - this is optional data
                )
            except asyncio.TimeoutError:
                print(f"[SELLER] Agent fetch timeout - skipping agent details (optional)")
                agents_all = []
            except Exception as agent_error:
                print(f"[SELLER] Error batch fetching agents: {agent_error}")
                agents_all = []  # Continue without agent data
        
        agents_by_id = {a.get("id"): a for a in agents_all if a.get("id")}
        
        # Enhance inquiries with pre-fetched data
        enhanced_inquiries = []
        for inquiry in inquiries_list:
            prop_id = inquiry.get("property_id")
            user_id_inquiry = inquiry.get("user_id")
            
            # Get property details from pre-fetched data
            property_info = properties_by_id.get(prop_id, {})
            
            # Get assigned agent details from pre-fetched data
            assigned_agent = None
            agent_id = property_info.get("agent_id") or property_info.get("assigned_agent_id")
            if agent_id and agent_id in agents_by_id:
                agent = agents_by_id[agent_id]
                assigned_agent = {
                    "id": agent.get("id"),
                    "name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip(),
                    "email": agent.get("email"),
                    "phone": agent.get("phone_number"),
                }
            
            # Add assigned_agent to property_info
            if assigned_agent:
                property_info["assigned_agent"] = assigned_agent
            
            # Get user details from pre-fetched data
            user_info = users_by_id.get(user_id_inquiry, {}) if user_id_inquiry else {}
            
            # Always include customer details from inquiry fields (name, email, phone)
            # These are the primary customer contact details
            customer_details = {
                "name": inquiry.get("name", ""),
                "email": inquiry.get("email", ""),
                "phone": inquiry.get("phone", ""),
                "first_name": user_info.get("first_name", inquiry.get("name", "").split()[0] if inquiry.get("name") else ""),
                "last_name": user_info.get("last_name", " ".join(inquiry.get("name", "").split()[1:]) if inquiry.get("name") and len(inquiry.get("name", "").split()) > 1 else ""),
                "phone_number": user_info.get("phone_number", inquiry.get("phone", "")),
                "user_id": user_id_inquiry
            }
            
            # Merge user info with customer details (user info takes precedence for additional fields)
            if user_info:
                customer_details.update({
                    "id": user_info.get("id"),
                    "user_type": user_info.get("user_type"),
                    "city": user_info.get("city"),
                    "state": user_info.get("state"),
                    "email_verified": user_info.get("email_verified"),
                })
            
            enhanced_inquiry = {
                **inquiry,
                "property": property_info,
                "user": customer_details  # Always include customer details
            }
            enhanced_inquiries.append(enhanced_inquiry)
        
        result = {"success": True, "inquiries": enhanced_inquiries, "total": len(enhanced_inquiries)}
        # Cache result for 1 minute for faster subsequent requests
        cache.set(cache_key, result, ttl=120)  # Cache for 2 minutes for faster repeated requests
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Get inquiries error: {e}")
        print(f"[SELLER] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch inquiries: {str(e)}")

@router.get("/bookings")
async def get_seller_bookings(
    request: Request,
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get bookings for seller's properties"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[SELLER] Fetching bookings for user: {user_id}")
        
        # Optimize: Build filters directly without fetching all properties first
        if property_id:
            # Direct property filter
            filters = {"property_id": property_id}
            # Verify the property belongs to this seller
            properties = await db.select("properties", filters={"id": property_id, "added_by": user_id}, limit=1)
            if not properties:
                return {"success": True, "bookings": [], "total": 0}
        else:
            # Get seller's property IDs - increase limit to get all properties
            properties = await db.select("properties", filters={"added_by": user_id}, limit=1000)  # Increased to get all properties
            property_ids = [p.get("id") for p in (properties or [])]
            
            if not property_ids:
                return {"success": True, "bookings": [], "total": 0}
            
            filters = {"property_id": {"in": property_ids}}
        
        if status:
            filters["status"] = status
        
        # Get bookings with limit and ordering - increase limit to get all bookings
        import asyncio
        try:
            bookings = await asyncio.wait_for(
                db.select("bookings", filters=filters, limit=min(limit or 1000, 1000), order_by="created_at", ascending=False),
                    timeout=3.0  # Increased timeout to handle more bookings
            )
        except asyncio.TimeoutError:
            print(f"[SELLER] Bookings query timeout for user: {user_id}")
            return {"success": True, "bookings": [], "total": 0}
        bookings_list = bookings or []
        
        # Early return if no bookings
        if not bookings_list:
            return {"success": True, "bookings": [], "total": 0}
        
        # Apply offset manually if needed (for pagination)
        if offset and offset > 0:
            bookings_list = bookings_list[offset:]
        
        # Batch fetch all related data to avoid N+1 queries (performance optimization)
        # Increase limits to get all related data
        property_ids_from_bookings = list(set([b.get("property_id") for b in bookings_list if b.get("property_id")]))[:200]  # Increased to get more properties
        user_ids_from_bookings = list(set([b.get("user_id") for b in bookings_list if b.get("user_id")]))[:200]  # Increased to get more users
        
        # Fetch all properties, agents, users, and booking counts in parallel with timeouts
        import asyncio
        
        try:
            # Execute queries in parallel only if we have IDs to fetch, with timeouts
            if property_ids_from_bookings and user_ids_from_bookings:
                properties_all, users_all, all_bookings_for_count = await asyncio.wait_for(
                    asyncio.gather(
                        db.select("properties", filters={"id": {"in": property_ids_from_bookings}}, limit=200),
                        db.select("users", filters={"id": {"in": user_ids_from_bookings}}, limit=200),
                        db.select("bookings", filters={"property_id": {"in": property_ids_from_bookings}}, limit=500),
                        return_exceptions=True
                    ),
                    timeout=5.0  # 5 second timeout
                )
            elif property_ids_from_bookings:
                properties_all = await asyncio.wait_for(
                    db.select("properties", filters={"id": {"in": property_ids_from_bookings}}, limit=200),
                    timeout=3.0
                )
                users_all = []
                all_bookings_for_count = await asyncio.wait_for(
                    db.select("bookings", filters={"property_id": {"in": property_ids_from_bookings}}, limit=500),
                    timeout=3.0
                )
            elif user_ids_from_bookings:
                properties_all = []
                users_all = await asyncio.wait_for(
                    db.select("users", filters={"id": {"in": user_ids_from_bookings}}, limit=200),
                    timeout=3.0
                )
                all_bookings_for_count = []
            else:
                properties_all, users_all, all_bookings_for_count = [], [], []
            
            # Handle exceptions
            if isinstance(properties_all, Exception):
                print(f"[SELLER] Error fetching properties: {properties_all}")
                properties_all = []
            if isinstance(users_all, Exception):
                print(f"[SELLER] Error fetching users: {users_all}")
                users_all = []
            if isinstance(all_bookings_for_count, Exception):
                print(f"[SELLER] Error fetching booking counts: {all_bookings_for_count}")
                all_bookings_for_count = []
        except asyncio.TimeoutError:
            print(f"[SELLER] Batch fetch timeout - returning partial data")
            properties_all, users_all, all_bookings_for_count = [], [], []
        except Exception as batch_error:
            print(f"[SELLER] Batch fetch error: {batch_error}")
            properties_all, users_all, all_bookings_for_count = [], [], []
        
        # Group by ID for O(1) lookup
        properties_by_id = {p.get("id"): p for p in properties_all if p.get("id")}
        users_by_id = {u.get("id"): u for u in users_all if u.get("id")}
        
        # Count bookings per property
        bookings_count_by_property = {}
        for b in all_bookings_for_count:
            prop_id = b.get("property_id")
            if prop_id:
                bookings_count_by_property[prop_id] = bookings_count_by_property.get(prop_id, 0) + 1
        
        # Get unique agent IDs from properties (limit to prevent too many queries)
        # Skip agent fetching if we're running low on time - this is optional data
        agent_ids = list(set([
            p.get("agent_id") or p.get("assigned_agent_id") 
            for p in properties_all 
            if p.get("agent_id") or p.get("assigned_agent_id")
        ]))[:10]  # Reduced from 20 to 10 agents max
        
        # Fetch agents in parallel with shorter timeout (optional data - can skip if slow)
        agents_all = []
        if agent_ids:
            try:
                agents_all = await asyncio.wait_for(
                    db.select("users", filters={"id": {"in": agent_ids}}, limit=10),
                    timeout=2.0  # Reduced from 3 to 2 seconds - this is optional data
                )
            except asyncio.TimeoutError:
                print(f"[SELLER] Agent fetch timeout - skipping agent details (optional)")
                agents_all = []
            except Exception as agent_error:
                print(f"[SELLER] Error batch fetching agents: {agent_error}")
                agents_all = []  # Continue without agent data
        
        agents_by_id = {a.get("id"): a for a in agents_all if a.get("id")}
        
        # Enhance bookings with pre-fetched data - include all bookings (including cancelled)
        enhanced_bookings = []
        for booking in bookings_list:
            prop_id = booking.get("property_id")
            user_id_booking = booking.get("user_id")
            
            # Get property details from pre-fetched data
            property_info = properties_by_id.get(prop_id, {})
            
            # Don't skip bookings - show all bookings including cancelled ones
            # Only skip if property_info is completely empty and we need property details
            if not property_info and prop_id:
                # Try to fetch property if not found in pre-fetched data
                try:
                    prop_data = await db.select("properties", filters={"id": prop_id}, limit=1)
                    if prop_data:
                        property_info = prop_data[0]
                        properties_by_id[prop_id] = property_info
                except Exception as prop_err:
                    print(f"[SELLER] Could not fetch property {prop_id}: {prop_err}")
                    # Continue anyway - booking will show with minimal property info
            
            # Get assigned agent details from pre-fetched data
            assigned_agent = None
            agent_id = property_info.get("agent_id") or property_info.get("assigned_agent_id")
            if agent_id and agent_id in agents_by_id:
                agent = agents_by_id[agent_id]
                assigned_agent = {
                    "id": agent.get("id"),
                    "name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip(),
                    "email": agent.get("email"),
                    "phone": agent.get("phone_number"),
                }
            
            # Add assigned_agent to property_info
            if assigned_agent:
                property_info["assigned_agent"] = assigned_agent
            
            # Get bookings count from pre-fetched data
            property_info["bookings_count"] = bookings_count_by_property.get(prop_id, 0)
            
            # Get user details from pre-fetched data
            user_info = users_by_id.get(user_id_booking, {}) if user_id_booking else {}
            
            enhanced_booking = {
                **booking,
                "property": property_info,
                "user": user_info
            }
            enhanced_bookings.append(enhanced_booking)
        
        print(f"[SELLER] Found {len(enhanced_bookings)} bookings")
        return {"success": True, "bookings": enhanced_bookings, "total": len(enhanced_bookings)}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Get bookings error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch bookings: {str(e)}")

@router.post("/bookings/{booking_id}/update-status")
async def update_booking_status(
    booking_id: str,
    request: Request
):
    """Update booking status (confirm, cancel, reschedule)"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get request data
        data = await request.json()
        new_status = data.get("status")
        new_date = data.get("tour_date")
        notes = data.get("notes", "")
        
        if not new_status:
            raise HTTPException(status_code=400, detail="Status is required")
        
        print(f"[SELLER] Updating booking {booking_id} status to {new_status}")
        
        # Verify booking belongs to seller
        booking_data = await db.select("bookings", filters={"id": booking_id})
        if not booking_data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        booking = booking_data[0]
        property_id = booking.get("property_id")
        
        # Check if property belongs to seller
        property_data = await db.select("properties", filters={"id": property_id, "added_by": user_id})
        if not property_data:
            raise HTTPException(status_code=403, detail="Not authorized to update this booking")
        
        # Update booking
        update_data = {
            "status": new_status,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        if new_date:
            update_data["tour_date"] = new_date
        
        if notes:
            update_data["notes"] = notes
        
        await db.update("bookings", update_data, {"id": booking_id})
        
        print(f"[SELLER] Booking {booking_id} updated successfully")
        return {"success": True, "message": f"Booking status updated to {new_status}"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Update booking status error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update booking status: {str(e)}")

@router.post("/inquiries/{inquiry_id}/respond")
async def respond_to_inquiry(
    inquiry_id: str,
    request: Request
):
    """Respond to an inquiry"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get request data
        data = await request.json()
        response_message = data.get("message")
        
        if not response_message:
            raise HTTPException(status_code=400, detail="Response message is required")
        
        print(f"[SELLER] Responding to inquiry {inquiry_id}")
        
        # Verify inquiry belongs to seller's property
        inquiry_data = await db.select("inquiries", filters={"id": inquiry_id})
        if not inquiry_data:
            raise HTTPException(status_code=404, detail="Inquiry not found")
        
        inquiry = inquiry_data[0]
        property_id = inquiry.get("property_id")
        
        # Check if property belongs to seller
        property_data = await db.select("properties", filters={"id": property_id, "added_by": user_id})
        if not property_data:
            raise HTTPException(status_code=403, detail="Not authorized to respond to this inquiry")
        
        # Update inquiry with response
        update_data = {
            "status": "responded",
            "response_message": response_message,
            "responded_at": dt.datetime.utcnow().isoformat(),
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        await db.update("inquiries", update_data, {"id": inquiry_id})
        
        print(f"[SELLER] Inquiry {inquiry_id} responded successfully")
        return {"success": True, "message": "Response sent successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Respond to inquiry error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to respond to inquiry: {str(e)}")

@router.get("/properties/{property_id}")
async def get_seller_property_details(property_id: str, request: Request):
    """Get detailed information about a specific property for seller"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[SELLER] Fetching property details for property {property_id}")
        
        # Get property
        properties = await db.select("properties", filters={"id": property_id})
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_data = properties[0]
        
        # Verify seller owns this property
        if property_data.get("added_by") != user_id and property_data.get("owner_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this property")
        
        property_id_val = property_data.get("id")
        
        # Get inquiries count
        inquiries = await db.select("inquiries", filters={"property_id": property_id_val})
        inquiries_count = len(inquiries or [])
        
        # Get bookings count
        bookings = await db.select("bookings", filters={"property_id": property_id_val})
        bookings_count = len(bookings or [])
        
        # Get views count
        views = await db.select("property_views", filters={"property_id": property_id_val})
        views_count = len(views or [])
        
        # Get assigned agent details
        assigned_agent = None
        agent_id = property_data.get("agent_id") or property_data.get("assigned_agent_id")
        if agent_id:
            try:
                agents = await db.select("users", filters={"id": agent_id})
                if agents:
                    agent = agents[0]
                    assigned_agent = {
                        "id": agent.get("id"),
                        "name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip(),
                        "email": agent.get("email"),
                        "phone": agent.get("phone_number"),
                        "assigned_at": property_data.get("assigned_at")
                    }
            except Exception as agent_error:
                print(f"[SELLER] Error fetching agent details: {agent_error}")
        
        # Get property images
        property_images = []
        try:
            image_docs = await db.select("documents", filters={
                "entity_type": "property",
                "entity_id": property_id_val
            })
            if image_docs:
                for doc in image_docs:
                    file_type = doc.get('file_type', '')
                    if file_type.startswith('image/'):
                        image_url = doc.get("file_path") or doc.get("url")
                        if image_url:
                            # If it's not already a full URL, convert file_path to public URL
                            if not (image_url.startswith('http://') or image_url.startswith('https://')):
                                try:
                                    # Property images are in 'property-images' bucket
                                    public_url = db.supabase_client.storage.from_('property-images').get_public_url(image_url)
                                    image_url = public_url
                                except Exception as url_error:
                                    print(f"[SELLER] Failed to get public URL for {image_url}: {url_error}")
                                    # Try documents bucket as fallback
                                    try:
                                        public_url = db.supabase_client.storage.from_('documents').get_public_url(image_url)
                                        image_url = public_url
                                    except:
                                        # Use file_path as-is if conversion fails
                                        pass
                            property_images.append(image_url)
        except Exception as img_error:
            print(f"[SELLER] Error fetching property images: {img_error}")
            import traceback
            print(traceback.format_exc())
        
        enhanced_property = {
            **property_data,
            "inquiries_count": inquiries_count,
            "bookings_count": bookings_count,
            "views_count": views_count,
            "assigned_agent": assigned_agent,
            "images": property_images
        }
        
        print(f"[SELLER] Property details fetched successfully")
        return {"success": True, "property": enhanced_property}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Get property details error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch property details: {str(e)}")

@router.get("/properties/{property_id}/views")
async def get_seller_property_views(property_id: str, request: Request, limit: Optional[int] = Query(100)):
    """Get property views for seller (name and date only, no contact info)"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[SELLER] Fetching views for property {property_id}")
        
        # Verify seller owns this property
        properties = await db.select("properties", filters={"id": property_id})
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_data = properties[0]
        if property_data.get("added_by") != user_id and property_data.get("owner_id") != user_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this property's views")
        
        # Get views
        views = await db.select("property_views", filters={"property_id": property_id}, limit=limit)
        views_list = views or []
        
        # Format views - only name and date (no email/phone)
        formatted_views = []
        for view in views_list:
            viewer_name = "Anonymous"
            viewer_id = view.get("user_id")
            
            # If user_id exists, get user name (but not email/phone)
            if viewer_id:
                try:
                    users = await db.select("users", filters={"id": viewer_id})
                    if users:
                        user = users[0]
                        first_name = user.get("first_name", "")
                        last_name = user.get("last_name", "")
                        viewer_name = f"{first_name} {last_name}".strip() or "User"
                except Exception:
                    viewer_name = "User"
            
            formatted_views.append({
                "id": view.get("id"),
                "viewer_name": viewer_name,
                "viewed_at": view.get("viewed_at") or view.get("created_at")
            })
        
        # Sort by viewed_at descending (most recent first)
        formatted_views.sort(key=lambda x: x.get("viewed_at", ""), reverse=True)
        
        print(f"[SELLER] Found {len(formatted_views)} views for property {property_id}")
        return {"success": True, "views": formatted_views}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SELLER] Get property views error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch property views: {str(e)}")
