from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional, List, Dict, Any
from ..db.supabase_client import db
from ..core.security import get_current_user_claims
import datetime as dt
import traceback
import uuid

router = APIRouter()

@router.get("/dashboard/stats")
async def get_buyer_dashboard_stats(request: Request):
    """Get comprehensive buyer dashboard statistics"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[BUYER] Fetching dashboard stats for user: {user_id}")
        
        # Get buyer's inquiries
        inquiries = await db.select("inquiries", filters={"user_id": user_id})
        inquiries_list = inquiries or []
        
        # Get buyer's bookings
        bookings = await db.select("bookings", filters={"user_id": user_id})
        bookings_list = bookings or []
        
        # Get saved properties from the saved_properties table
        saved_properties = await db.select("saved_properties", filters={"user_id": user_id})
        saved_properties_list = saved_properties or []
        
        # Calculate stats
        total_inquiries = len(inquiries_list)
        total_bookings = len(bookings_list)
        completed_tours = len([b for b in bookings_list if b.get("status") == "completed"])
        pending_bookings = len([b for b in bookings_list if b.get("status") == "pending"])
        confirmed_bookings = len([b for b in bookings_list if b.get("status") == "confirmed"])
        
        # Get favorite locations from inquiries/bookings
        property_ids = list(set([i.get("property_id") for i in inquiries_list] + [b.get("property_id") for b in bookings_list]))
        favorite_locations = 0
        preferred_property_types = []
        
        if property_ids:
            properties = await db.select("properties", filters={"id": {"in": property_ids}})
            if properties:
                favorite_locations = len(set(p.get("city") for p in properties if p.get("city")))
                preferred_property_types = list(set(p.get("property_type") for p in properties if p.get("property_type")))
        
        stats = {
            "saved_properties": len(saved_properties_list),
            "total_inquiries": total_inquiries,
            "total_bookings": total_bookings,
            "completed_tours": completed_tours,
            "pending_bookings": pending_bookings,
            "confirmed_bookings": confirmed_bookings,
            "favorite_locations": favorite_locations,
            "preferred_property_types": preferred_property_types,
            "response_rate": round((confirmed_bookings / max(total_inquiries, 1)) * 100, 2)
        }
        
        print(f"[BUYER] Dashboard stats calculated: {stats}")
        return {"success": True, "stats": stats}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Dashboard stats error: {e}")
        print(f"[BUYER] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard stats: {str(e)}")

@router.get("/saved-properties")
async def get_saved_properties(
    request: Request,
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get buyer's saved properties"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[BUYER] Fetching saved properties for user: {user_id}")
        
        # Get saved properties from saved_properties table
        saved = await db.select("saved_properties", filters={"user_id": user_id}, limit=limit, offset=offset)
        saved_list = saved or []
        
        if not saved_list:
            return {"success": True, "properties": [], "total": 0}
        
        # Get property IDs
        property_ids = [s.get("property_id") for s in saved_list]
        
        # Get property details
        properties = await db.select("properties", filters={"id": {"in": property_ids}})
        properties_list = properties or []
        
        # Enhance properties with saved info (notes, saved_at)
        property_map = {p.get("id"): p for p in properties_list}
        enhanced_properties = []
        
        for saved_item in saved_list:
            prop_id = saved_item.get("property_id")
            if prop_id in property_map:
                prop = property_map[prop_id].copy()
                prop["is_saved"] = True
                prop["saved_at"] = saved_item.get("saved_at")
                prop["saved_notes"] = saved_item.get("notes")
                enhanced_properties.append(prop)
        
        print(f"[BUYER] Found {len(enhanced_properties)} saved properties")
        return {"success": True, "properties": enhanced_properties, "total": len(enhanced_properties)}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Get saved properties error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch saved properties: {str(e)}")

@router.post("/save-property")
async def save_property(
    request: Request
):
    """Save a property to buyer's favorites"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get request data
        data = await request.json()
        property_id = data.get("property_id")
        notes = data.get("notes", "")
        
        if not property_id:
            raise HTTPException(status_code=400, detail="Property ID is required")
        
        print(f"[BUYER] Saving property {property_id} for user: {user_id}")
        
        # Use the database function to toggle saved property
        try:
            result = await db.rpc("toggle_saved_property", {
                "property_id_param": property_id,
                "user_id_param": user_id
            })
            
            # If newly saved and notes provided, update notes
            if result.get("saved") and notes:
                await db.update("saved_properties", 
                    {"notes": notes},
                    {"user_id": user_id, "property_id": property_id}
                )
            
            print(f"[BUYER] Property {property_id} toggled: {result}")
            return {"success": True, "message": result.get("message"), "saved": result.get("saved")}
        except Exception as e:
            # Fallback to direct insert if function not available
            print(f"[BUYER] RPC failed, using direct insert: {e}")
            save_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "property_id": property_id,
                "notes": notes,
                "saved_at": dt.datetime.utcnow().isoformat(),
                "created_at": dt.datetime.utcnow().isoformat()
            }
            await db.insert("saved_properties", save_data)
            print(f"[BUYER] Property {property_id} saved successfully")
            return {"success": True, "message": "Property saved to favorites", "saved": True}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Save property error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save property: {str(e)}")

@router.delete("/unsave-property/{property_id}")
async def unsave_property(
    property_id: str,
    request: Request
):
    """Remove a property from buyer's favorites"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[BUYER] Removing property {property_id} from favorites for user: {user_id}")
        
        # Delete from saved_properties table
        await db.delete("saved_properties", {"user_id": user_id, "property_id": property_id})
        
        print(f"[BUYER] Property {property_id} removed from favorites")
        return {"success": True, "message": "Property removed from favorites"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Unsave property error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove property: {str(e)}")

@router.get("/inquiries")
async def get_buyer_inquiries(
    request: Request,
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get buyer's inquiries"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[BUYER] Fetching inquiries for user: {user_id}")
        
        # Build filters
        filters = {"user_id": user_id}
        if status:
            filters["status"] = status
        
        # Get inquiries
        inquiries = await db.select("inquiries", filters=filters, limit=limit, offset=offset)
        inquiries_list = inquiries or []
        
        # Enhance inquiries with property details
        enhanced_inquiries = []
        for inquiry in inquiries_list:
            prop_id = inquiry.get("property_id")
            property_data = await db.select("properties", filters={"id": prop_id})
            property_info = property_data[0] if property_data else {}
            
            enhanced_inquiry = {
                **inquiry,
                "property": property_info
            }
            enhanced_inquiries.append(enhanced_inquiry)
        
        print(f"[BUYER] Found {len(enhanced_inquiries)} inquiries")
        return {"success": True, "inquiries": enhanced_inquiries, "total": len(enhanced_inquiries)}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Get inquiries error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch inquiries: {str(e)}")

@router.get("/bookings")
async def get_buyer_bookings(
    request: Request,
    status: Optional[str] = Query(None),
    limit: Optional[int] = Query(20),
    offset: Optional[int] = Query(0)
):
    """Get buyer's bookings"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        print(f"[BUYER] Fetching bookings for user: {user_id}")
        
        # Build filters
        filters = {"user_id": user_id}
        if status:
            filters["status"] = status
        
        # Get bookings
        bookings = await db.select("bookings", filters=filters, limit=limit, offset=offset)
        bookings_list = bookings or []
        
        # Enhance bookings with property details and filter out sold properties
        enhanced_bookings = []
        for booking in bookings_list:
            prop_id = booking.get("property_id")
            property_data = await db.select("properties", filters={"id": prop_id})
            property_info = property_data[0] if property_data else {}
            
            # Skip bookings for sold properties
            prop_status = (property_info.get('status') or '').lower().strip()
            if prop_status == 'sold':
                print(f"[BUYER] Skipping booking for sold property: {prop_id}")
                continue
            
            enhanced_booking = {
                **booking,
                "property": property_info
            }
            enhanced_bookings.append(enhanced_booking)
        
        print(f"[BUYER] Found {len(enhanced_bookings)} bookings")
        return {"success": True, "bookings": enhanced_bookings, "total": len(enhanced_bookings)}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Get bookings error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch bookings: {str(e)}")

@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: str,
    request: Request
):
    """Cancel a booking"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get request data
        data = await request.json()
        cancellation_reason = data.get("reason", "Cancelled by buyer")
        
        print(f"[BUYER] Cancelling booking {booking_id} for user: {user_id}")
        
        # Verify booking belongs to buyer
        booking_data = await db.select("bookings", filters={"id": booking_id, "user_id": user_id})
        if not booking_data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Get existing notes to preserve them
        existing_notes = booking_data[0].get("notes", "") or ""
        
        # Update booking status
        # Note: cancellation_reason column doesn't exist in database schema
        # Store cancellation reason in notes field instead
        cancellation_note = f"Cancelled by buyer: {cancellation_reason}"
        if existing_notes:
            updated_notes = f"{existing_notes}\n\n{cancellation_note}"
        else:
            updated_notes = cancellation_note
        
        update_data = {
            "status": "cancelled",
            "notes": updated_notes,
            # Note: cancelled_at column doesn't exist in database schema
            # The cancelled_at timestamp is tracked via status='cancelled' and updated_at
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        # Remove cancelled_at if it was added (it doesn't exist in schema)
        if "cancelled_at" in update_data:
            del update_data["cancelled_at"]
        
        await db.update("bookings", update_data, {"id": booking_id})
        
        print(f"[BUYER] Booking {booking_id} cancelled successfully")
        return {"success": True, "message": "Booking cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Cancel booking error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel booking: {str(e)}")

@router.post("/bookings/{booking_id}/reschedule")
async def reschedule_booking(
    booking_id: str,
    request: Request
):
    """Reschedule a booking"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_id = claims.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        # Get request data
        data = await request.json()
        new_date = data.get("tour_date")
        notes = data.get("notes", "")
        
        if not new_date:
            raise HTTPException(status_code=400, detail="New tour date is required")
        
        print(f"[BUYER] Rescheduling booking {booking_id} to {new_date} for user: {user_id}")
        
        # Verify booking belongs to buyer
        booking_data = await db.select("bookings", filters={"id": booking_id, "user_id": user_id})
        if not booking_data:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Update booking
        update_data = {
            "tour_date": new_date,
            "status": "pending",  # Reset to pending for seller approval
            "notes": notes,
            "updated_at": dt.datetime.utcnow().isoformat()
        }
        
        await db.update("bookings", update_data, {"id": booking_id})
        
        print(f"[BUYER] Booking {booking_id} rescheduled successfully")
        return {"success": True, "message": "Booking rescheduled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[BUYER] Reschedule booking error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reschedule booking: {str(e)}")
