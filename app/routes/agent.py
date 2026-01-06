from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional, List, Dict, Any
from ..db.supabase_client import db
from ..core.security import get_current_user_claims
import datetime as dt
import traceback
import uuid
import asyncio
import json

router = APIRouter()

@router.get("/dashboard/stats")
async def get_agent_dashboard_stats(request: Request):
    """Get comprehensive agent dashboard statistics"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[AGENT] Fetching dashboard stats for user: {user_id}")
        print(f"[AGENT] Agent ID (user_id): {user_id}")
        
        # Get agent's ASSIGNED properties only (not properties they just own)
        # Agents should only see properties where they are assigned as the agent
        # 1. agent_id - legacy assignment field
        # 2. assigned_agent_id - current assignment field
        # NOTE: We do NOT include owner_id - agents should only see assigned properties
        print(f"[AGENT] Querying ASSIGNED properties only for stats")
        print(f"[AGENT] OR conditions: agent_id={user_id} OR assigned_agent_id={user_id}")
        import asyncio
        try:
            properties_list = await asyncio.wait_for(
                db.select(
                    "properties", 
                    filters={
                        "or": [
                            {"agent_id": user_id},
                            {"assigned_agent_id": user_id}
                        ]
                    },
                    limit=100,  # Reduced from 1000 to 100 for performance
                    order_by="created_at",
                    ascending=False
                ),
                timeout=2.0  # 2 second timeout
            )
            properties_list = properties_list or []
            print(f"[AGENT] OR query returned {len(properties_list)} ASSIGNED properties for stats")
            
            # Log sample property IDs for debugging
            if properties_list:
                sample_ids = [p.get("id", "N/A")[:8] for p in properties_list[:3]]
                print(f"[AGENT] Sample property IDs: {sample_ids}")
                # Log assignment details for first property
                first_prop = properties_list[0]
                print(f"[AGENT] First property assignment - agent_id: {first_prop.get('agent_id')}, assigned_agent_id: {first_prop.get('assigned_agent_id')}")
        except asyncio.TimeoutError:
            print(f"[AGENT] Properties query timeout for user: {user_id}")
            properties_list = []
        except Exception as or_error:
            print(f"[AGENT] OR query failed, using separate queries: {or_error}")
            # Fallback to separate queries - ONLY assigned properties
            try:
                properties_agent_id, properties_assigned_id = await asyncio.wait_for(
                    asyncio.gather(
                        db.select("properties", filters={"agent_id": user_id}, limit=100),
                        db.select("properties", filters={"assigned_agent_id": user_id}, limit=100),
                        return_exceptions=True
                    ),
                    timeout=2.0
                )
                if isinstance(properties_agent_id, Exception):
                    properties_agent_id = []
                if isinstance(properties_assigned_id, Exception):
                    properties_assigned_id = []
            except asyncio.TimeoutError:
                print(f"[AGENT] Fallback queries timeout for user: {user_id}")
                properties_agent_id = []
                properties_assigned_id = []
            
            # Combine only assigned properties (NOT owner_id)
            all_properties = (properties_agent_id or []) + (properties_assigned_id or [])
            unique_properties = []
            seen_ids = set()
            
            for prop in all_properties:
                prop_id = prop.get("id")
                if prop_id and prop_id not in seen_ids:
                    seen_ids.add(prop_id)
                    unique_properties.append(prop)
            
            properties_list = unique_properties
        
        print(f"[AGENT] Found {len(properties_list)} total properties (assigned + owned)")
        
        # Calculate stats
        total_properties = len(properties_list)
        active_properties = len([p for p in properties_list if p.get("status") == "active"])
        pending_properties = len([p for p in properties_list if p.get("status") == "pending"])
        
        # Get inquiries for agent's properties - check both property assignments AND direct agent assignments
        property_ids = [p.get("id") for p in properties_list]
        total_inquiries = 0
        new_inquiries = 0
        responded_inquiries = 0
        
        try:
            # Get inquiries by property
            if property_ids:
                inquiries_by_property = await asyncio.wait_for(
                    db.select("inquiries", filters={"property_id": {"in": property_ids}}, limit=200, order_by="created_at", ascending=False),
                    timeout=2.0
                )
            else:
                inquiries_by_property = []
            
            # Get inquiries by direct agent assignment (from inquiries.assigned_agent_id) with timeout
            try:
                inquiries_by_agent = await asyncio.wait_for(
                    db.select("inquiries", filters={"assigned_agent_id": user_id}, limit=200, order_by="created_at", ascending=False),
                    timeout=1.5  # 1.5 second timeout for faster response
                )
            except asyncio.TimeoutError:
                print(f"[AGENT] Inquiries by agent query timeout")
                inquiries_by_agent = []
            except Exception as agent_inq_error:
                print(f"[AGENT] Error fetching inquiries by agent: {agent_inq_error}")
                inquiries_by_agent = []
            
            # Combine and deduplicate
            all_inquiries = (inquiries_by_property or []) + (inquiries_by_agent or [])
            seen_ids = set()
            inquiries_list = []
            for inquiry in all_inquiries:
                inquiry_id = inquiry.get("id")
                if inquiry_id and inquiry_id not in seen_ids:
                    seen_ids.add(inquiry_id)
                    inquiries_list.append(inquiry)
            
            total_inquiries = len(inquiries_list)
            new_inquiries = len([i for i in inquiries_list if i.get("status") == "new"])
            responded_inquiries = len([i for i in inquiries_list if i.get("status") == "responded"])
        except Exception as e:
            print(f"[AGENT] Error fetching inquiries for stats: {e}")
            print(f"[AGENT] Full traceback:")
            print(traceback.format_exc())
            # Fallback to property-based only
            try:
                if property_ids and len(property_ids) > 0:
                    inquiries = await db.select("inquiries", filters={"property_id": {"in": property_ids}})
                    inquiries_list = inquiries or []
                    total_inquiries = len(inquiries_list)
                    new_inquiries = len([i for i in inquiries_list if i.get("status") == "new"])
                    responded_inquiries = len([i for i in inquiries_list if i.get("status") == "responded"])
                else:
                    inquiries_list = []
                    total_inquiries = 0
                    new_inquiries = 0
                    responded_inquiries = 0
            except Exception as fallback_error:
                print(f"[AGENT] Fallback inquiry query also failed: {fallback_error}")
                inquiries_list = []
                total_inquiries = 0
                new_inquiries = 0
                responded_inquiries = 0
        
        # Get bookings for agent's properties - check both property assignments AND direct agent assignments
        total_bookings = 0
        pending_bookings = 0
        confirmed_bookings = 0
        completed_bookings = 0
        
        try:
            # Get bookings by property
            if property_ids:
                bookings_by_property = await db.select("bookings", filters={"property_id": {"in": property_ids}})
            else:
                bookings_by_property = []
            
            # Get bookings by direct agent assignment (from bookings.agent_id)
            bookings_by_agent = await db.select("bookings", filters={"agent_id": user_id})
            
            # Combine and deduplicate
            all_bookings = (bookings_by_property or []) + (bookings_by_agent or [])
            seen_ids = set()
            bookings_list = []
            for booking in all_bookings:
                booking_id = booking.get("id")
                if booking_id and booking_id not in seen_ids:
                    seen_ids.add(booking_id)
                    bookings_list.append(booking)
            
            total_bookings = len(bookings_list)
            pending_bookings = len([b for b in bookings_list if b.get("status") == "pending"])
            confirmed_bookings = len([b for b in bookings_list if b.get("status") == "confirmed"])
            completed_bookings = len([b for b in bookings_list if b.get("status") == "completed"])
        except Exception as e:
            print(f"[AGENT] Error fetching bookings for stats: {e}")
            print(f"[AGENT] Full traceback:")
            print(traceback.format_exc())
            # Fallback to property-based only
            try:
                if property_ids and len(property_ids) > 0:
                    import asyncio
                    bookings = await asyncio.wait_for(
                        db.select("bookings", filters={"property_id": {"in": property_ids}}, limit=200, order_by="created_at", ascending=False),
                        timeout=2.0
                    )
                    bookings_list = bookings or []
                    total_bookings = len(bookings_list)
                    pending_bookings = len([b for b in bookings_list if b.get("status") == "pending"])
                    confirmed_bookings = len([b for b in bookings_list if b.get("status") == "confirmed"])
                    completed_bookings = len([b for b in bookings_list if b.get("status") == "completed"])
                else:
                    bookings_list = []
                    total_bookings = 0
                    pending_bookings = 0
                    confirmed_bookings = 0
                    completed_bookings = 0
            except Exception as fallback_error:
                print(f"[AGENT] Fallback booking query also failed: {fallback_error}")
                bookings_list = []
                total_bookings = 0
                pending_bookings = 0
                confirmed_bookings = 0
                completed_bookings = 0
        
        # Calculate response rate
        response_rate = 0
        if total_inquiries > 0:
            response_rate = round((responded_inquiries / total_inquiries) * 100, 2)
        
        # Calculate conversion rate
        conversion_rate = 0
        if total_inquiries > 0:
            conversion_rate = round((total_bookings / total_inquiries) * 100, 2)
        
        # Calculate earnings and commissions from bookings
        total_earnings = 0
        monthly_commission = 0
        try:
            # Get commissions for this agent
            commissions = await db.select("commissions", filters={"agent_id": user_id}) or []
            total_earnings = sum(c.get('amount', 0) or 0 for c in commissions)
            
            # Calculate monthly commission (last 30 days)
            thirty_days_ago = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)).isoformat()
            monthly_commissions = [
                c for c in commissions 
                if c.get('created_at') and c.get('created_at') >= thirty_days_ago
            ]
            monthly_commission = sum(c.get('amount', 0) or 0 for c in monthly_commissions)
        except Exception as e:
            print(f"[AGENT] Error calculating earnings: {e}")
            # Fallback: estimate from bookings
            total_earnings = confirmed_bookings * 15000  # Estimate 15k per booking
            monthly_commission = confirmed_bookings * 15000 / 12
        
        # Calculate customer rating (if available)
        customer_rating = 4.8  # Default, can be calculated from reviews if available
        
        stats = {
            "total_properties": total_properties,
            "active_properties": active_properties,
            "pending_properties": pending_properties,
            "total_inquiries": total_inquiries,
            "new_inquiries": new_inquiries,
            "responded_inquiries": responded_inquiries,
            "total_bookings": total_bookings,
            "pending_bookings": pending_bookings,
            "confirmed_bookings": confirmed_bookings,
            "completed_bookings": completed_bookings,
            "response_rate": response_rate,
            "conversion_rate": conversion_rate,
            "total_earnings": total_earnings,
            "monthly_commission": monthly_commission,
            "customer_rating": customer_rating,
            "avg_response_time": "< 2 hours"  # Can be calculated from inquiry response times
        }
        
        print(f"[AGENT] Dashboard stats calculated: {stats}")
        return {"success": True, "stats": stats}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Dashboard stats error: {e}")
        print(f"[AGENT] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard stats: {str(e)}")

@router.get("/profile")
async def get_agent_profile(request: Request):
    """Get the current agent's full profile, including license and documents."""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        print(f"[AGENT] Fetching full profile for user: {user_id}")

        # Get agent's user data
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="Agent profile not found")
        
        agent_data = users[0]

        # Get agent's documents
        documents = await db.select("documents", filters={"entity_id": user_id}) or []
        
        # Add public URLs to documents
        for doc in documents:
            file_path = doc.get("file_path")
            if file_path:
                try:
                    # Check if file_path is already a full URL (starts with http)
                    if file_path.startswith('http://') or file_path.startswith('https://'):
                        # It's already a full URL, use it directly
                        doc['public_url'] = file_path
                    else:
                        # It's just a path, generate the public URL
                        public_url = db.supabase_client.storage.from_("documents").get_public_url(file_path)
                        doc['public_url'] = public_url
                except Exception as e:
                    print(f"Error generating public url for {file_path}: {e}")
                    doc['public_url'] = None
        
        # Combine into a single response
        full_profile = {
            "user": agent_data,
            "documents": documents
        }
        
        return full_profile

    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Get profile error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An error occurred while fetching agent profile.")

@router.get("/inquiries")
async def get_agent_inquiries(
    request: Request,
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get inquiries for agent's assigned properties"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[AGENT] Fetching inquiries for user: {user_id}")
        print(f"[AGENT] Agent ID (user_id): {user_id}")
        
        # Get agent's property IDs using OR query
        # Check all possible fields where agent might be assigned
        print(f"[AGENT] Querying properties for inquiries with OR filter")
        # Get only ASSIGNED properties (not properties they just own)
        print(f"[AGENT] OR conditions: agent_id={user_id} OR assigned_agent_id={user_id}")
        import asyncio
        try:
            all_properties = await asyncio.wait_for(
                db.select(
                    "properties", 
                    filters={
                        "or": [
                            {"agent_id": user_id},
                            {"assigned_agent_id": user_id}
                        ]
                    },
                    limit=1000,  # Increased to get all assigned properties
                    order_by="created_at",
                    ascending=False
                ),
                timeout=3.0  # Increased timeout for more properties
            )
            all_properties = all_properties or []
            property_ids = list(set([p.get("id") for p in all_properties if p.get("id")]))
            print(f"[AGENT] OR query returned {len(property_ids)} ASSIGNED property IDs for inquiries")
            if property_ids:
                print(f"[AGENT] Sample property IDs: {[pid[:8] for pid in property_ids[:3]]}")
        except asyncio.TimeoutError:
            print(f"[AGENT] Properties query timeout for inquiries")
            property_ids = []
        except Exception as or_error:
            print(f"[AGENT] OR query failed, using separate queries: {or_error}")
            # Fallback to separate queries - ONLY assigned properties with timeout
            try:
                properties_agent_id, properties_assigned_id = await asyncio.wait_for(
                    asyncio.gather(
                        db.select("properties", filters={"agent_id": user_id}, limit=1000),
                        db.select("properties", filters={"assigned_agent_id": user_id}, limit=1000),
                        return_exceptions=True
                    ),
                    timeout=3.0
                )
                if isinstance(properties_agent_id, Exception):
                    properties_agent_id = []
                if isinstance(properties_assigned_id, Exception):
                    properties_assigned_id = []
            except asyncio.TimeoutError:
                print(f"[AGENT] Fallback queries timeout for inquiries")
                properties_agent_id = []
                properties_assigned_id = []
            
            # Combine only assigned properties (NOT owner_id)
            all_properties = (properties_agent_id or []) + (properties_assigned_id or [])
            property_ids = list(set([p.get("id") for p in all_properties if p.get("id")]))
        
        print(f"[AGENT] Found {len(property_ids)} assigned properties for inquiries")
        if len(property_ids) > 0:
            print(f"[AGENT] Sample property IDs: {[pid[:8] if pid else 'N/A' for pid in property_ids[:3]]}")
        
        # Also check agent_property_assignments and agent_property_notifications tables
        # These tables link agents to properties even if properties table doesn't have agent_id/assigned_agent_id
        try:
            print(f"[AGENT] Checking agent_property_assignments table for user: {user_id}")
            assignments = await db.select("agent_property_assignments", filters={"agent_id": user_id}, limit=100)
            if assignments:
                assignment_property_ids = [a.get("property_id") for a in assignments if a.get("property_id")]
                property_ids.extend(assignment_property_ids)
                property_ids = list(set(property_ids))  # Deduplicate
                print(f"[AGENT] Found {len(assignment_property_ids)} additional properties from agent_property_assignments")
        except Exception as assign_error:
            print(f"[AGENT] Could not query agent_property_assignments: {assign_error}")
        
        try:
            print(f"[AGENT] Checking agent_property_notifications table for user: {user_id}")
            notifications = await db.select("agent_property_notifications", filters={"agent_id": user_id}, limit=100)
            if notifications:
                notification_property_ids = [n.get("property_id") for n in notifications if n.get("property_id")]
                property_ids.extend(notification_property_ids)
                property_ids = list(set(property_ids))  # Deduplicate
                print(f"[AGENT] Found {len(notification_property_ids)} additional properties from agent_property_notifications")
        except Exception as notif_error:
            print(f"[AGENT] Could not query agent_property_notifications: {notif_error}")
        
        print(f"[AGENT] Total property IDs after checking assignment tables: {len(property_ids)}")
        
        # Build filters - check both property assignments AND direct agent assignments in inquiries table
        # According to schema: inquiries table has assigned_agent_id field
        inquiries_list = []
        inquiries_by_property = []  # Initialize to avoid undefined variable errors
        inquiries_by_agent = []  # Initialize to avoid undefined variable errors
        try:
            # Get inquiries by property - use individual queries if "in" filter fails
            if property_ids and len(property_ids) > 0:
                print(f"[AGENT] Fetching inquiries for {len(property_ids)} properties")
                try:
                    inquiries_by_property = await asyncio.wait_for(
                        db.select("inquiries", filters={"property_id": {"in": property_ids}}, limit=min(limit or 1000, 1000), order_by="created_at", ascending=False),
                        timeout=3.0  # Increased timeout for more inquiries
                    )
                    print(f"[AGENT] Found {len(inquiries_by_property or [])} inquiries by property")
                except asyncio.TimeoutError:
                    print(f"[AGENT] Inquiries query timeout")
                    inquiries_by_property = []
                except Exception as in_error:
                    print(f"[AGENT] 'in' filter failed for inquiries: {in_error}")
                    inquiries_by_property = []
                    # Deduplicate
                    seen_ids = set()
                    unique_inquiries = []
                    for inquiry in inquiries_by_property:
                        inquiry_id = inquiry.get("id")
                        if inquiry_id and inquiry_id not in seen_ids:
                            seen_ids.add(inquiry_id)
                            unique_inquiries.append(inquiry)
                    inquiries_by_property = unique_inquiries
                    print(f"[AGENT] Found {len(inquiries_by_property)} inquiries by property (fallback method)")
            else:
                print(f"[AGENT] No property IDs, skipping property-based inquiry query")
            
            # Get inquiries by direct agent assignment (from inquiries.assigned_agent_id)
            # Also check if there's an agent_id field in inquiries table
            print(f"[AGENT] Fetching inquiries assigned directly to agent: {user_id}")
            import asyncio
            try:
                inquiries_by_agent = await asyncio.wait_for(
                    db.select("inquiries", filters={"assigned_agent_id": user_id}, limit=min(limit or 1000, 1000), order_by="created_at", ascending=False),
                    timeout=3.0  # Increased timeout for more inquiries
                )
            except asyncio.TimeoutError:
                print(f"[AGENT] Inquiries by agent query timeout")
                inquiries_by_agent = []
            except Exception as agent_inq_error:
                print(f"[AGENT] Error fetching inquiries by agent: {agent_inq_error}")
                inquiries_by_agent = []
            print(f"[AGENT] Found {len(inquiries_by_agent or [])} inquiries by assigned_agent_id")
            
            # Also check agent_id field if it exists (for backward compatibility)
            try:
                inquiries_by_agent_id = await db.select("inquiries", filters={"agent_id": user_id}, limit=limit or 1000)
                if inquiries_by_agent_id:
                    print(f"[AGENT] Found {len(inquiries_by_agent_id)} inquiries by agent_id")
                    # Merge with existing inquiries_by_agent
                    all_agent_inquiries = (inquiries_by_agent or []) + inquiries_by_agent_id
                    seen_ids = set()
                    inquiries_by_agent = []
                    for inquiry in all_agent_inquiries:
                        inquiry_id = inquiry.get("id")
                        if inquiry_id and inquiry_id not in seen_ids:
                            seen_ids.add(inquiry_id)
                            inquiries_by_agent.append(inquiry)
                    print(f"[AGENT] Total unique inquiries by agent assignment: {len(inquiries_by_agent)}")
            except Exception as agent_id_error:
                print(f"[AGENT] Note: agent_id field may not exist in inquiries table: {agent_id_error}")
            
            # Combine and deduplicate
            all_inquiries = (inquiries_by_property or []) + (inquiries_by_agent or [])
            seen_ids = set()
            for inquiry in all_inquiries:
                inquiry_id = inquiry.get("id")
                if inquiry_id and inquiry_id not in seen_ids:
                    seen_ids.add(inquiry_id)
                    inquiries_list.append(inquiry)
            
            print(f"[AGENT] Total unique inquiries after deduplication: {len(inquiries_list)}")
            
            # Apply status filter if provided
            if status:
                before_status = len(inquiries_list)
                inquiries_list = [i for i in inquiries_list if i.get("status") == status]
                print(f"[AGENT] After status filter ({status}): {len(inquiries_list)} (was {before_status})")
            
            # Apply property_id filter if provided
            if property_id:
                before_prop = len(inquiries_list)
                inquiries_list = [i for i in inquiries_list if i.get("property_id") == property_id]
                print(f"[AGENT] After property_id filter: {len(inquiries_list)} (was {before_prop})")
            
            # Apply limit
            if limit and limit > 0:
                before_limit = len(inquiries_list)
                inquiries_list = inquiries_list[:limit]
                print(f"[AGENT] After limit ({limit}): {len(inquiries_list)} (was {before_limit})")
                
        except Exception as e:
            print(f"[AGENT] Error with complex inquiry query: {e}")
            print(f"[AGENT] Full traceback:")
            import traceback
            print(traceback.format_exc())
            # Fallback to simple property-based query
            try:
                if property_ids and len(property_ids) > 0:
                    filters = {"property_id": {"in": property_ids}}
                    if property_id:
                        filters["property_id"] = property_id
                    if status:
                        filters["status"] = status
                    inquiries = await asyncio.wait_for(
                        db.select("inquiries", filters=filters, limit=min(limit or 100, 200), order_by="created_at", ascending=False),
                        timeout=1.5
                    )
                    inquiries_list = inquiries or []
                    print(f"[AGENT] Fallback query returned {len(inquiries_list)} inquiries")
                else:
                    # Try direct agent assignment only
                    inquiries = await asyncio.wait_for(
                        db.select("inquiries", filters={"assigned_agent_id": user_id}, limit=min(limit or 100, 200), order_by="created_at", ascending=False),
                        timeout=1.5
                    )
                    inquiries_list = inquiries or []
                    print(f"[AGENT] Fallback direct assignment query returned {len(inquiries_list)} inquiries")
            except Exception as fallback_error:
                print(f"[AGENT] Fallback query also failed: {fallback_error}")
                inquiries_list = []
        
        # Enhance inquiries with property and user details - BATCH FETCH to avoid N+1 queries
        enhanced_inquiries = []
        
        # Collect all unique IDs for batch fetching
        property_ids = list(set([inquiry.get("property_id") for inquiry in inquiries_list if inquiry.get("property_id")]))
        user_ids = list(set([inquiry.get("user_id") for inquiry in inquiries_list if inquiry.get("user_id")]))
        
        # Batch fetch all properties and users in parallel with timeout
        import asyncio
        properties_map = {}
        users_map = {}
        
        try:
            tasks = []
            if property_ids:
                tasks.append(db.select("properties", filters={"id": {"in": property_ids}}, limit=len(property_ids)))
            if user_ids:
                tasks.append(db.select("users", filters={"id": {"in": user_ids}}, limit=len(user_ids)))
            
            if tasks:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=1.5  # 1.5 second timeout for faster response
                )
                
                if property_ids:
                    properties_all = results[0] if not isinstance(results[0], Exception) else []
                    properties_map = {p.get("id"): p for p in properties_all if p.get("id")}
                
                if user_ids:
                    users_all = results[1] if not isinstance(results[1], Exception) else []
                    users_map = {u.get("id"): u for u in users_all if u.get("id")}
        except asyncio.TimeoutError:
            print(f"[AGENT] Batch fetch timeout for inquiries enhancement")
        except Exception as batch_error:
            print(f"[AGENT] Batch fetch error: {batch_error}")
        
        # Now enhance inquiries using the batch-fetched data
        for inquiry in inquiries_list:
            prop_id = inquiry.get("property_id")
            user_id_inquiry = inquiry.get("user_id")
            
            # Get property details from map
            property_info = properties_map.get(prop_id, {})
            
            # Get user details from map
            user_info = users_map.get(user_id_inquiry, {}) if user_id_inquiry else {}
            
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
        
        print(f"[AGENT] Returning {len(enhanced_inquiries)} inquiries")
        
        # Ensure response format matches frontend expectations
        response = {
            "success": True, 
            "inquiries": enhanced_inquiries, 
            "total": len(enhanced_inquiries)
        }
        
        print(f"[AGENT] Final response - success: {response['success']}, total: {response['total']}, inquiries array length: {len(response['inquiries'])}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Get inquiries error: {e}")
        print(f"[AGENT] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch inquiries: {str(e)}")

@router.get("/bookings")
async def get_agent_bookings(
    request: Request,
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get bookings for agent's assigned properties"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[AGENT] Fetching bookings for user: {user_id}")
        print(f"[AGENT] Agent ID (user_id): {user_id}")
        
        # Get agent's property IDs using OR query
        # Check all possible fields where agent might be assigned
        print(f"[AGENT] Querying properties for bookings with OR filter")
        # Get only ASSIGNED properties (not properties they just own)
        print(f"[AGENT] OR conditions: agent_id={user_id} OR assigned_agent_id={user_id}")
        import asyncio
        try:
            all_properties = await asyncio.wait_for(
                db.select(
                    "properties", 
                    filters={
                        "or": [
                            {"agent_id": user_id},
                            {"assigned_agent_id": user_id}
                        ]
                    },
                    limit=1000,  # Increased to get all assigned properties
                    order_by="created_at",
                    ascending=False
                ),
                timeout=3.0  # Increased timeout for more properties
            )
            all_properties = all_properties or []
            property_ids = list(set([p.get("id") for p in all_properties if p.get("id")]))
            print(f"[AGENT] OR query returned {len(property_ids)} ASSIGNED property IDs for bookings")
            if property_ids:
                print(f"[AGENT] Sample property IDs: {[pid[:8] for pid in property_ids[:3]]}")
        except asyncio.TimeoutError:
            print(f"[AGENT] Properties query timeout for bookings")
            property_ids = []
        except Exception as or_error:
            print(f"[AGENT] OR query failed, using separate queries: {or_error}")
            # Fallback to separate queries - ONLY assigned properties with timeout
            try:
                properties_agent_id, properties_assigned_id = await asyncio.wait_for(
                    asyncio.gather(
                        db.select("properties", filters={"agent_id": user_id}, limit=100),
                        db.select("properties", filters={"assigned_agent_id": user_id}, limit=100),
                        return_exceptions=True
                    ),
                    timeout=2.0
                )
                if isinstance(properties_agent_id, Exception):
                    properties_agent_id = []
                if isinstance(properties_assigned_id, Exception):
                    properties_assigned_id = []
            except asyncio.TimeoutError:
                print(f"[AGENT] Fallback queries timeout for bookings")
                properties_agent_id = []
                properties_assigned_id = []
            
            # Combine only assigned properties (NOT owner_id)
            all_properties = (properties_agent_id or []) + (properties_assigned_id or [])
            property_ids = list(set([p.get("id") for p in all_properties if p.get("id")]))
        
        print(f"[AGENT] Found {len(property_ids)} assigned properties for bookings")
        if len(property_ids) > 0:
            print(f"[AGENT] Sample property IDs: {[pid[:8] if pid else 'N/A' for pid in property_ids[:3]]}")
        
        # Also check agent_property_assignments and agent_property_notifications tables
        # These tables link agents to properties even if properties table doesn't have agent_id/assigned_agent_id
        try:
            print(f"[AGENT] Checking agent_property_assignments table for user: {user_id}")
            assignments = await db.select("agent_property_assignments", filters={"agent_id": user_id}, limit=100)
            if assignments:
                assignment_property_ids = [a.get("property_id") for a in assignments if a.get("property_id")]
                property_ids.extend(assignment_property_ids)
                property_ids = list(set(property_ids))  # Deduplicate
                print(f"[AGENT] Found {len(assignment_property_ids)} additional properties from agent_property_assignments")
        except Exception as assign_error:
            print(f"[AGENT] Could not query agent_property_assignments: {assign_error}")
        
        try:
            print(f"[AGENT] Checking agent_property_notifications table for user: {user_id}")
            notifications = await db.select("agent_property_notifications", filters={"agent_id": user_id}, limit=100)
            if notifications:
                notification_property_ids = [n.get("property_id") for n in notifications if n.get("property_id")]
                property_ids.extend(notification_property_ids)
                property_ids = list(set(property_ids))  # Deduplicate
                print(f"[AGENT] Found {len(notification_property_ids)} additional properties from agent_property_notifications")
        except Exception as notif_error:
            print(f"[AGENT] Could not query agent_property_notifications: {notif_error}")
        
        print(f"[AGENT] Total property IDs after checking assignment tables: {len(property_ids)}")
        
        # Build filters - check both property assignments AND direct agent assignments in bookings table
        # According to schema: bookings table has agent_id field
        booking_filters = []
        
        # Bookings for agent's assigned properties with timeout
        bookings_by_property = []
        if property_ids:
            try:
                bookings_by_property = await asyncio.wait_for(
                    db.select("bookings", filters={"property_id": {"in": property_ids}}, limit=min(limit or 1000, 1000), order_by="created_at", ascending=False),
                    timeout=3.0  # Increased timeout for more bookings
                )
            except asyncio.TimeoutError:
                print(f"[AGENT] Bookings query timeout")
                bookings_by_property = []
            except Exception as in_error:
                print(f"[AGENT] 'in' filter failed for bookings: {in_error}")
                bookings_by_property = []
                # Deduplicate
                seen_ids = set()
                unique_bookings = []
                for booking in bookings_by_property:
                    booking_id = booking.get("id")
                    if booking_id and booking_id not in seen_ids:
                        seen_ids.add(booking_id)
                        unique_bookings.append(booking)
                bookings_by_property = unique_bookings
        
        # Bookings directly assigned to this agent (from bookings.agent_id) with timeout
        print(f"[AGENT] Fetching bookings assigned directly to agent: {user_id}")
        try:
            bookings_by_agent = await asyncio.wait_for(
                db.select("bookings", filters={"agent_id": user_id}, limit=min(limit or 1000, 1000), order_by="created_at", ascending=False),
                timeout=3.0  # Increased timeout for more bookings
            )
        except asyncio.TimeoutError:
            print(f"[AGENT] Bookings by agent query timeout")
            bookings_by_agent = []
        except Exception as agent_book_error:
            print(f"[AGENT] Error fetching bookings by agent: {agent_book_error}")
            bookings_by_agent = []
        print(f"[AGENT] Found {len(bookings_by_agent or [])} bookings by agent_id")
        
        # Log sample booking IDs for debugging
        if bookings_by_agent:
            sample_booking_ids = [b.get("id", "N/A")[:8] for b in bookings_by_agent[:3]]
            print(f"[AGENT] Sample booking IDs by agent: {sample_booking_ids}")
        
        # Also check bookings for assigned properties where agent_id might be NULL
        # This handles cases where bookings exist but agent_id wasn't set during creation
        # We already have bookings_by_property which includes all bookings for assigned properties
        # regardless of agent_id, so this should cover it. But let's add more logging.
        print(f"[AGENT] Bookings by property count: {len(bookings_by_property or [])}")
        if bookings_by_property:
            sample_property_booking_ids = [b.get("id", "N/A")[:8] for b in bookings_by_property[:3]]
            print(f"[AGENT] Sample booking IDs by property: {sample_property_booking_ids}")
            # Log agent_id status for these bookings
            agent_id_status = {}
            for b in bookings_by_property[:5]:
                bid = b.get("id", "N/A")[:8]
                aid = b.get("agent_id")
                agent_id_status[bid] = "set" if aid else "NULL"
            print(f"[AGENT] Agent ID status in property bookings: {agent_id_status}")
        
        # Combine bookings from properties and direct agent assignment
        all_bookings = (bookings_by_property or []) + (bookings_by_agent or [])
        seen_ids = set()
        bookings_list = []
        for booking in all_bookings:
            booking_id = booking.get("id")
            if booking_id and booking_id not in seen_ids:
                seen_ids.add(booking_id)
                bookings_list.append(booking)
        
        print(f"[AGENT] Combined {len(bookings_list)} total bookings (property-based: {len(bookings_by_property or [])}, agent-based: {len(bookings_by_agent or [])})")
        
        # Apply additional filters
        if property_id:
            bookings_list = [b for b in bookings_list if b.get("property_id") == property_id]
        if status:
            bookings_list = [b for b in bookings_list if b.get("status") == status]
        
        # Bookings are already fetched and filtered above, now enhance with property and user details
        try:
            # Apply limit if provided
            if limit and limit > 0:
                before_limit = len(bookings_list)
                bookings_list = bookings_list[:limit]
                print(f"[AGENT] After limit ({limit}): {len(bookings_list)} (was {before_limit})")
                
        except Exception as e:
            print(f"[AGENT] Error with complex booking query: {e}")
            print(f"[AGENT] Full traceback:")
            import traceback
            print(traceback.format_exc())
            # Fallback to simple property-based query
            try:
                if property_ids and len(property_ids) > 0:
                    filters = {"property_id": {"in": property_ids}}
                    if property_id:
                        filters["property_id"] = property_id
                    if status:
                        filters["status"] = status
                    bookings = await db.select("bookings", filters=filters, limit=limit or 100)
                    bookings_list = bookings or []
                    print(f"[AGENT] Fallback query returned {len(bookings_list)} bookings")
                else:
                    # Try direct agent assignment only
                    bookings = await db.select("bookings", filters={"agent_id": user_id}, limit=limit or 100)
                    bookings_list = bookings or []
                    print(f"[AGENT] Fallback direct assignment query returned {len(bookings_list)} bookings")
            except Exception as fallback_error:
                print(f"[AGENT] Fallback query also failed: {fallback_error}")
                bookings_list = []
        
        # Enhance bookings with property and user details
        # NOTE: Don't filter out sold properties - agents should see all bookings for their assigned properties
        enhanced_bookings = []
        for booking in bookings_list:
            prop_id = booking.get("property_id")
            user_id_booking = booking.get("user_id")
            
            # Get property details
            property_data = await db.select("properties", filters={"id": prop_id})
            property_info = property_data[0] if property_data else {}
            
            # Don't skip bookings for sold properties - agents need to see all bookings
            # The property status doesn't affect whether an agent should see the booking
            
            # Get user details
            user_info = {}
            if user_id_booking:
                user_data = await db.select("users", filters={"id": user_id_booking})
                user_info = user_data[0] if user_data else {}
            
            # Include customer information from booking fields if user not found
            # This handles cases where booking was made by non-registered users
            customer_info = {
                "name": booking.get("name") or f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip() or "Guest",
                "email": booking.get("email") or user_info.get("email") or "N/A",
                "phone": booking.get("phone") or user_info.get("phone_number") or "N/A",
                "user_id": user_id_booking,
                "user_type": user_info.get("user_type") if user_info else None
            }
            
            enhanced_booking = {
                **booking,
                "property": property_info,
                "user": user_info,
                "customer": customer_info  # Add clear customer info
            }
            enhanced_bookings.append(enhanced_booking)
        
        print(f"[AGENT] Returning {len(enhanced_bookings)} bookings")
        print(f"[AGENT] Booking breakdown - by property: {len(bookings_by_property or [])}, by agent assignment: {len(bookings_by_agent or [])}")
        
        # Ensure response format matches frontend expectations
        response = {
            "success": True, 
            "bookings": enhanced_bookings, 
            "total": len(enhanced_bookings)
        }
        
        print(f"[AGENT] Final response - success: {response['success']}, total: {response['total']}, bookings array length: {len(response['bookings'])}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Get bookings error: {e}")
        print(f"[AGENT] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch bookings: {str(e)}")

@router.get("/properties")
async def get_agent_properties(
    request: Request,
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get properties assigned to the agent"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[AGENT] Fetching properties for user: {user_id}")
        print(f"[AGENT] Agent ID (user_id): {user_id}")
        
        # Get agent's ASSIGNED properties only (not properties they just own)
        # Agents should only see properties where they are assigned as the agent
        # 1. agent_id - legacy field for assignment
        # 2. assigned_agent_id - current field for assignment
        # NOTE: We do NOT include owner_id - agents should only see assigned properties, not properties they own
        print(f"[AGENT] Querying ASSIGNED properties only: agent_id={user_id} OR assigned_agent_id={user_id}")
        
        import asyncio
        try:
            # Use OR query to get all assigned properties in one call with timeout
            unique_properties = await asyncio.wait_for(
                db.select(
                    "properties", 
                    filters={
                        "or": [
                            {"agent_id": user_id},
                            {"assigned_agent_id": user_id}
                        ]
                    },
                    limit=min(limit or 100, 200),  # Reduced limit for performance
                    offset=offset,
                    order_by="created_at",
                    ascending=False
                ),
                timeout=2.0  # 2 second timeout
            )
            unique_properties = unique_properties or []
            print(f"[AGENT] OR query returned {len(unique_properties)} ASSIGNED properties")
            
            # Log assignment breakdown for debugging
            if unique_properties:
                agent_id_count = len([p for p in unique_properties if p.get("agent_id") == user_id])
                assigned_agent_id_count = len([p for p in unique_properties if p.get("assigned_agent_id") == user_id])
                print(f"[AGENT] Property assignment breakdown - agent_id: {agent_id_count}, assigned_agent_id: {assigned_agent_id_count}")
                sample_ids = [p.get("id", "N/A")[:8] for p in unique_properties[:3]]
                print(f"[AGENT] Sample property IDs: {sample_ids}")
        except asyncio.TimeoutError:
            print(f"[AGENT] Properties query timeout for user: {user_id}")
            unique_properties = []
        except Exception as or_error:
            print(f"[AGENT] OR query failed, falling back to separate queries: {or_error}")
            # Fallback to separate queries - ONLY assigned properties with timeout
            try:
                properties_agent_id, properties_assigned_id = await asyncio.wait_for(
                    asyncio.gather(
                        db.select("properties", filters={"agent_id": user_id}, limit=min(limit or 100, 200), offset=offset, order_by="created_at", ascending=False),
                        db.select("properties", filters={"assigned_agent_id": user_id}, limit=min(limit or 100, 200), offset=offset, order_by="created_at", ascending=False),
                        return_exceptions=True
                    ),
                    timeout=2.0
                )
                if isinstance(properties_agent_id, Exception):
                    properties_agent_id = []
                if isinstance(properties_assigned_id, Exception):
                    properties_assigned_id = []
            except asyncio.TimeoutError:
                print(f"[AGENT] Fallback queries timeout for user: {user_id}")
                properties_agent_id = []
                properties_assigned_id = []
            
            print(f"[AGENT] Properties with agent_id: {len(properties_agent_id or [])}")
            print(f"[AGENT] Properties with assigned_agent_id: {len(properties_assigned_id or [])}")
            
            # Combine only assigned properties (NOT owner_id)
            all_properties = (properties_agent_id or []) + (properties_assigned_id or [])
            unique_properties = []
            seen_ids = set()
            
            for prop in all_properties:
                prop_id = prop.get("id")
                if prop_id and prop_id not in seen_ids:
                    seen_ids.add(prop_id)
                    unique_properties.append(prop)
        
        print(f"[AGENT] Found {len(unique_properties)} total unique assigned properties")
        if len(unique_properties) > 0:
            print(f"[AGENT] Sample property IDs: {[p.get('id')[:8] if p.get('id') else 'N/A' for p in unique_properties[:3]]}")
            # Debug: Show assignment details for first property
            first_prop = unique_properties[0]
            print(f"[AGENT] First property - agent_id: {first_prop.get('agent_id')}, assigned_agent_id: {first_prop.get('assigned_agent_id')}, owner_id: {first_prop.get('owner_id')}")
        
        # Apply status filter if provided
        if status:
            unique_properties = [p for p in unique_properties if p.get("status") == status]
        
        # Apply limit and offset
        # If limit is very high (>= 1000), return all properties without pagination
        if limit and limit >= 1000:
            paginated_properties = unique_properties
            print(f"[AGENT] Returning all {len(paginated_properties)} properties (limit >= 1000, no pagination)")
        else:
            start_idx = offset or 0
            end_idx = start_idx + (limit or 20)
            paginated_properties = unique_properties[start_idx:end_idx]
            print(f"[AGENT] Returning {len(paginated_properties)} properties (paginated from {len(unique_properties)} total)")
        if unique_properties:
            agent_id_count = len([p for p in unique_properties if p.get("agent_id") == user_id])
            assigned_agent_id_count = len([p for p in unique_properties if p.get("assigned_agent_id") == user_id])
            print(f"[AGENT] Property assignment breakdown - agent_id: {agent_id_count}, assigned_agent_id: {assigned_agent_id_count}")
        
        # Fetch images from documents table for all properties (similar to seller endpoint)
        property_ids = [p.get("id") for p in paginated_properties if p.get("id")]
        images_by_property = {}
        cover_photos_by_property = {}
        
        if property_ids:
            try:
                # #region agent log
                log_entry = {
                    "location": "agent.py:1087",
                    "message": "Fetching property images from documents",
                    "data": {
                        "propertyCount": len(property_ids),
                        "propertyIds": [pid[:8] for pid in property_ids[:5]]
                    },
                    "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000),
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A"
                }
                try:
                    with open(".cursor/debug.log", 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry) + '\n')
                except:
                    pass
                # #endregion
                
                # Query documents individually to avoid UUID serialization issues with "in" filter
                # The Supabase Python client has issues with UUID arrays in "in" filters
                images_all = []
                if property_ids:
                    # Query in batches to avoid too many individual queries
                    batch_size = 10
                    for i in range(0, len(property_ids), batch_size):
                        batch = property_ids[i:i + batch_size]
                        batch_tasks = []
                        for prop_id in batch:
                            batch_tasks.append(db.select("documents", filters={"entity_type": "property", "entity_id": prop_id}))
                        try:
                            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                            for result in batch_results:
                                if isinstance(result, Exception):
                                    print(f"[AGENT] Error fetching documents batch: {result}")
                                elif result:
                                    images_all.extend(result)
                        except Exception as batch_error:
                            print(f"[AGENT] Error in documents batch query: {batch_error}")
                
                # #region agent log
                log_entry2 = {
                    "location": "agent.py:1100",
                    "message": "Images fetched from documents",
                    "data": {
                        "totalDocuments": len(images_all or []),
                        "imageDocuments": len([d for d in (images_all or []) if d.get("file_type", "").startswith("image/")])
                    },
                    "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000),
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A"
                }
                try:
                    with open(".cursor/debug.log", 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry2) + '\n')
                except:
                    pass
                # #endregion
                
                for doc in images_all or []:
                    prop_id = doc.get("entity_id")
                    file_type = doc.get("file_type", "")
                    doc_category = doc.get("document_category", "")
                    if prop_id and file_type.startswith("image/"):
                        # Check public_url first, then url, then file_path (same as seller endpoint)
                        image_url = doc.get("public_url") or doc.get("url") or doc.get("file_path")
                        if image_url:
                            # If it's not already a full URL, convert file_path to public URL
                            if not (image_url.startswith('http://') or image_url.startswith('https://')):
                                original_path = image_url
                                try:
                                    # Property images are in 'property-images' bucket
                                    public_url = db.supabase_client.storage.from_('property-images').get_public_url(image_url)
                                    image_url = public_url
                                except Exception as url_error:
                                    print(f"[AGENT] Failed to get public URL for {image_url}: {url_error}")
                                    # Try documents bucket as fallback
                                    try:
                                        public_url = db.supabase_client.storage.from_('documents').get_public_url(image_url)
                                        image_url = public_url
                                    except:
                                        # Use file_path as-is if conversion fails
                                        pass
                            
                            # Only add if it's a valid HTTP/HTTPS URL
                            if image_url.startswith('http://') or image_url.startswith('https://'):
                                # Check if this is a cover photo
                                if doc_category == 'cover_photo':
                                    cover_photos_by_property[prop_id] = image_url
                                else:
                                    # Regular property image
                                    if prop_id not in images_by_property:
                                        images_by_property[prop_id] = []
                                    images_by_property[prop_id].append(image_url)
            except Exception as img_error:
                print(f"[AGENT] Error fetching images: {img_error}")
                # #region agent log
                log_entry3 = {
                    "location": "agent.py:1140",
                    "message": "Error fetching images",
                    "data": {
                        "error": str(img_error)
                    },
                    "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000),
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "A"
                }
                try:
                    with open(".cursor/debug.log", 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry3) + '\n')
                except:
                    pass
                # #endregion
        
        # Enhance properties with images
        enhanced_properties = []
        for property_data in paginated_properties:
            property_id = property_data.get("id")
            
            # Get property images from pre-fetched data
            property_images = images_by_property.get(property_id, [])
            cover_image = cover_photos_by_property.get(property_id) or property_data.get("cover_image")
            
            # If no cover_image but we have images, use first image as cover_image (user request)
            if not cover_image and property_images and len(property_images) > 0:
                cover_image = property_images[0]
            
            # If cover_image exists, add it to the beginning of images array
            if cover_image and cover_image not in property_images:
                property_images = [cover_image] + property_images
            
            # #region agent log
            log_entry4 = {
                "location": "agent.py:1200",
                "message": "Property enhanced with images",
                "data": {
                    "propertyId": property_id[:8] if property_id else "N/A",
                    "imagesCount": len(property_images),
                    "hasCoverImage": bool(cover_image),
                    "coverImageSource": "cover_photos_by_property" if cover_photos_by_property.get(property_id) else ("first_image" if not cover_photos_by_property.get(property_id) and property_images else "property_data"),
                    "firstImageUrl": property_images[0] if property_images else None
                },
                "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000),
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "A"
            }
            try:
                with open(".cursor/debug.log", 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry4) + '\n')
            except:
                pass
            # #endregion
            
            enhanced_property = {
                **property_data,
                "images": property_images,
                "cover_image": cover_image or property_data.get("cover_image")
            }
            
            enhanced_properties.append(enhanced_property)
        
        response = {"success": True, "properties": enhanced_properties, "total": len(unique_properties)}
        print(f"[AGENT] Final response - success: {response['success']}, total: {response['total']}, properties array length: {len(response['properties'])}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Get properties error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch properties: {str(e)}")

@router.get("/property-assignments/{notification_id}")
async def get_property_assignment_details(
    notification_id: str, 
    request: Request,
    token: Optional[str] = Query(None)
):
    """Get details of a specific property assignment notification (token-based, no login required)"""
    try:
        # Get notification details
        notifications = await db.select("agent_property_notifications", filters={"id": notification_id})
        if not notifications:
            raise HTTPException(status_code=404, detail="Assignment notification not found")
        
        notification = notifications[0]
        
        # Verify secure token (allows access without login)
        if token:
            # Token-based authentication (from email link)
            stored_token = notification.get("secure_token")
            if not stored_token or stored_token != token:
                raise HTTPException(status_code=403, detail="Invalid or expired token")
        else:
            # Fall back to regular authentication (if agent is logged in)
            claims = get_current_user_claims(request)
            if not claims:
                raise HTTPException(status_code=401, detail="Authentication required. Please use the link from your email.")
            
            user_id = claims.get("sub")
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid authentication")
            
            # Verify this notification is for the current agent
            if notification.get("agent_id") != user_id:
                raise HTTPException(status_code=403, detail="You don't have permission to view this assignment")
        
        # Get property details
        property_id = notification.get("property_id")
        properties = await db.select("properties", filters={"id": property_id})
        
        return {
            "success": True,
            "notification": notification,
            "property": properties[0] if properties else None
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Error fetching assignment details: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/property-assignments/{notification_id}/accept")
async def accept_property_assignment(
    notification_id: str,
    request: Request,
    token: Optional[str] = Query(None)
):
    """Accept a property assignment (token-based, no login required)"""
    try:
        # Get notification to extract agent_id
        notifications = await db.select("agent_property_notifications", filters={"id": notification_id})
        if not notifications:
            raise HTTPException(status_code=404, detail="Assignment notification not found")
        
        notification = notifications[0]
        agent_id = notification.get("agent_id")
        
        # Verify secure token (allows access without login)
        if token:
            # Token-based authentication (from email link)
            stored_token = notification.get("secure_token")
            if not stored_token or stored_token != token:
                raise HTTPException(status_code=403, detail="Invalid or expired token. Please use the link from your email.")
        else:
            # Fall back to regular authentication (if agent is logged in)
            claims = get_current_user_claims(request)
            if not claims:
                raise HTTPException(status_code=401, detail="Authentication required. Please use the link from your email.")
            
            user_id = claims.get("sub")
            if not user_id or user_id != agent_id:
                raise HTTPException(status_code=403, detail="You don't have permission to accept this assignment")
        
        print(f"[AGENT] Agent {agent_id} accepting assignment {notification_id}")
        
        # Call the sequential notification service to handle acceptance
        from ..services.sequential_agent_notification import SequentialAgentNotificationService
        result = await SequentialAgentNotificationService.accept_assignment(notification_id, agent_id)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Error accepting assignment: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/property-assignments/{notification_id}/reject")
async def reject_property_assignment(
    notification_id: str,
    request: Request,
    token: Optional[str] = Query(None)
):
    """Reject a property assignment (token-based, no login required)"""
    try:
        # Get notification to extract agent_id
        notifications = await db.select("agent_property_notifications", filters={"id": notification_id})
        if not notifications:
            raise HTTPException(status_code=404, detail="Assignment notification not found")
        
        notification = notifications[0]
        agent_id = notification.get("agent_id")
        
        # Verify secure token (allows access without login)
        if token:
            # Token-based authentication (from email link)
            stored_token = notification.get("secure_token")
            if not stored_token or stored_token != token:
                raise HTTPException(status_code=403, detail="Invalid or expired token. Please use the link from your email.")
        else:
            # Fall back to regular authentication (if agent is logged in)
            claims = get_current_user_claims(request)
            if not claims:
                raise HTTPException(status_code=401, detail="Authentication required. Please use the link from your email.")
            
            user_id = claims.get("sub")
            if not user_id or user_id != agent_id:
                raise HTTPException(status_code=403, detail="You don't have permission to reject this assignment")
        
        payload = await request.json()
        reason = payload.get("reason", "No reason provided")
        
        print(f"[AGENT] Agent {agent_id} rejecting assignment {notification_id}, reason: {reason}")
        
        # Call the sequential notification service to handle rejection
        from ..services.sequential_agent_notification import SequentialAgentNotificationService
        result = await SequentialAgentNotificationService.reject_assignment(notification_id, agent_id, reason)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Error rejecting assignment: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pending-assignments")
async def get_pending_property_assignments(request: Request):
    """Get pending property assignment notifications for the agent"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[AGENT] Fetching pending assignments for user: {user_id}")
        
        # Get pending notifications for this agent
        notifications = await db.select("agent_property_notifications", filters={
            "agent_id": user_id,
            "status": "pending"
        })
        
        notifications_list = notifications or []
        
        # Enhance with property details
        enhanced_notifications = []
        for notification in notifications_list:
            property_id = notification.get("property_id")
            property_data = None
            
            if property_id:
                properties = await db.select("properties", filters={"id": property_id})
                if properties:
                    property_data = properties[0]
            
            enhanced_notifications.append({
                **notification,
                "property": property_data
            })
        
        # Sort by sent_at descending (most recent first)
        enhanced_notifications.sort(
            key=lambda x: x.get("sent_at", ""), 
            reverse=True
        )
        
        print(f"[AGENT] Found {len(enhanced_notifications)} pending assignments")
        return {"success": True, "notifications": enhanced_notifications, "total": len(enhanced_notifications)}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Get pending assignments error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending assignments: {str(e)}")

@router.post("/properties/{property_id}/request-status-change")
async def request_property_status_change(
    property_id: str,
    payload: dict,
    request: Request
):
    """Agent requests to change property status (requires admin approval)"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Verify user is an agent - check both role (from JWT) and user_type (from database)
        user_role = claims.get("role") or claims.get("user_type")
        if user_role != "agent":
            # Double-check by querying database
            users = await db.select("users", filters={"id": user_id}, limit=1)
            if not users:
                raise HTTPException(status_code=404, detail="User not found")
            db_user_type = users[0].get("user_type", "").lower()
            if db_user_type != "agent":
                print(f"[AGENT] Permission denied - JWT role: {user_role}, DB user_type: {db_user_type}")
                raise HTTPException(status_code=403, detail="Only agents can request status changes")
        
        new_status = payload.get("status", "").lower()
        reason = payload.get("reason", "")
        buyer_name = payload.get("buyer_name", "")  # Capture buyer name when marking as sold
        
        if not new_status:
            raise HTTPException(status_code=400, detail="Status is required")
        
        # Only allow certain status changes that require approval
        allowed_statuses = ["sold", "rented", "inactive", "withdrawn"]
        if new_status not in allowed_statuses:
            raise HTTPException(status_code=400, detail=f"Status '{new_status}' cannot be requested. Allowed: {', '.join(allowed_statuses)}")
        
        # Verify property exists and agent has access
        properties = await db.select("properties", filters={"id": property_id})
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_data = properties[0]
        
        # Check if agent is assigned to this property
        assigned_agent_id = property_data.get("assigned_agent_id") or property_data.get("agent_id")
        if assigned_agent_id != user_id:
            raise HTTPException(status_code=403, detail="You are not assigned to this property")
        
        current_status = property_data.get("status", "active")
        if current_status == new_status:
            raise HTTPException(status_code=400, detail=f"Property is already {new_status}")
        
        # Create status change request - store in notifications table for admin review
        request_id = str(uuid.uuid4())
        
        # Get agent name from database
        users = await db.select("users", filters={"id": user_id}, limit=1)
        agent_name = "Agent"
        if users:
            agent = users[0]
            agent_name = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip() or "Agent"
        
        # Build message with buyer name if provided
        message = f"Agent {agent_name} requested to change property '{property_data.get('title', property_id)}' status from {current_status} to {new_status}"
        if new_status == "sold" and buyer_name:
            message += f". Buyer: {buyer_name}"
        
        # Store request in notifications table for admin
        # For admin notifications, we'll use user_id=None which should be fetched by admin endpoint
        notification_id = str(uuid.uuid4())
        
        # Build comprehensive metadata
        metadata_dict = {
            "request_id": request_id,
            "agent_id": user_id,
            "agent_name": agent_name,
            "current_status": current_status,
            "requested_status": new_status,
            "reason": reason or f"Agent requested status change from {current_status} to {new_status}",
            "buyer_name": buyer_name if new_status == "sold" else None,
            "property_title": property_data.get('title', 'Unknown Property'),
            "property_city": property_data.get('city', ''),
            "property_state": property_data.get('state', ''),
            "property_price": str(property_data.get('price', '')) or str(property_data.get('monthly_rent', ''))
        }
        
        notification_data = {
            "id": notification_id,
            "user_id": None,  # Admin notification - None means it's for all admins
            "type": "property_status_request",
            "title": f"Property Status Change Request",
            "message": message,
            "entity_type": "property",
            "entity_id": property_id,
            "read": False,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "metadata": json.dumps(metadata_dict)  # Convert to JSON string immediately
        }
        
        print(f"[AGENT] Creating status change notification: {notification_id}")
        print(f"[AGENT] Property: {property_data.get('title', property_id)}")
        print(f"[AGENT] Agent: {agent_name} (ID: {user_id})")
        print(f"[AGENT] Buyer: {buyer_name if new_status == 'sold' else 'N/A'}")
        print(f"[AGENT] Status: {current_status} -> {new_status}")
        
        try:
            # Metadata is already JSON string from above
            await db.insert("notifications", notification_data)
            print(f"[AGENT] ✅ Status change request notification created successfully: {notification_id}")
            print(f"[AGENT] Notification will appear in admin approvals page")
            
            # Verify the notification was created
            try:
                verify_notif = await db.select("notifications", filters={"id": notification_id}, limit=1)
                if verify_notif:
                    print(f"[AGENT] ✅ Verified notification exists in database")
                else:
                    print(f"[AGENT] ⚠️ WARNING: Notification not found after creation")
            except Exception as verify_error:
                print(f"[AGENT] Could not verify notification: {verify_error}")
            
        except Exception as notif_error:
            print(f"[AGENT] Failed to create notification: {notif_error}")
            print(traceback.format_exc())
            # Fallback: email admin directly
            try:
                from ..services.email import send_email
                admin_users = await db.select("users", filters={"user_type": "admin", "status": "active"}, limit=10)
                for admin in admin_users:
                    email_html = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #162e5a;">Property Status Change Request</h2>
                        <p>Agent <strong>{agent_name}</strong> has requested to change property status.</p>
                        <div style="background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                            <p><strong>Property:</strong> {property_data.get('title', property_id)}</p>
                            <p><strong>Property ID:</strong> {property_id}</p>
                            <p><strong>Current Status:</strong> {current_status}</p>
                            <p><strong>Requested Status:</strong> {new_status}</p>
                            <p><strong>Reason:</strong> {reason or 'No reason provided'}</p>
                            {f'<p><strong>Buyer Name:</strong> {buyer_name}</p>' if buyer_name else ''}
                        </div>
                        <p>Please review and approve/reject this request in the admin panel.</p>
                    </div>
                    """
                    await send_email(
                        admin.get("email"),
                        f"Property Status Change Request - {property_data.get('title', property_id)}",
                        email_html
                    )
                    print(f"[AGENT] Sent status change request email to admin: {admin.get('email')}")
            except Exception as email_error:
                print(f"[AGENT] Failed to send email: {email_error}")
        
        print(f"[AGENT] Status change request created: {request_id}")
        
        return {
            "success": True,
            "message": f"Status change request submitted successfully. Admin approval required.",
            "notification_id": notification_data.get('id'),
            "request_id": request_id,
            "current_status": current_status,
            "requested_status": new_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[AGENT] Error creating status change request: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to create status change request: {str(e)}")
