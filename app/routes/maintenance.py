"""
Maintenance requests routes for property management
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
from ..db.supabase_client import db
from ..core.security import get_current_user_claims
import datetime as dt
import uuid
import traceback

router = APIRouter()

@router.get("/maintenance")
async def get_maintenance_requests(
    tenant_id: Optional[str] = Query(None),
    property_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None)
) -> List[Dict[str, Any]]:
    """Get maintenance requests with optional filters"""
    try:
        print(f"[MAINTENANCE] GET requests - tenant_id: {tenant_id}, property_id: {property_id}, status: {status}")
        
        # Build filters
        filters = {}
        if tenant_id:
            filters['tenant_id'] = tenant_id
        if property_id:
            filters['property_id'] = property_id
        if status:
            filters['status'] = status.upper()
        
        # Fetch from database
        requests = await db.select("maintenance_requests", filters=filters)
        
        print(f"[MAINTENANCE] Found {len(requests or [])} maintenance requests")
        return requests or []
        
    except Exception as e:
        print(f"[MAINTENANCE] Error fetching requests: {e}")
        print(f"[MAINTENANCE] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to fetch maintenance requests: {str(e)}")

@router.post("/maintenance")
async def create_maintenance_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new maintenance request"""
    try:
        print(f"[MAINTENANCE] Creating new maintenance request")
        print(f"[MAINTENANCE] Request data: {request_data}")
        
        # Generate ID and timestamps
        request_id = str(uuid.uuid4())
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        
        # Prepare maintenance request data
        maintenance_request = {
            "id": request_id,
            "tenant_id": request_data.get("tenant_id"),
            "property_id": request_data.get("property_id"),
            "title": request_data.get("title", ""),
            "description": request_data.get("description", ""),
            "category": request_data.get("category", "Other"),
            "priority": request_data.get("priority", "MEDIUM").upper(),
            "status": request_data.get("status", "PENDING").upper(),
            "estimated_cost": request_data.get("estimated_cost"),
            "completion_date": request_data.get("completion_date"),
            "created_at": now,
            "updated_at": now
        }
        
        # Validate required fields
        if not maintenance_request["tenant_id"]:
            raise HTTPException(status_code=400, detail="tenant_id is required")
        if not maintenance_request["title"]:
            raise HTTPException(status_code=400, detail="title is required")
        if not maintenance_request["description"]:
            raise HTTPException(status_code=400, detail="description is required")
        
        # Insert into database
        try:
            result = await db.insert("maintenance_requests", maintenance_request)
            print(f"[MAINTENANCE] Request created with ID: {request_id}")
            
            # Return the created request
            return {
                **maintenance_request,
                "message": "Maintenance request created successfully"
            }
            
        except Exception as insert_error:
            print(f"[MAINTENANCE] Database insert failed: {insert_error}")
            raise HTTPException(status_code=500, detail=f"Failed to create maintenance request: {str(insert_error)}")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[MAINTENANCE] Create request error: {e}")
        print(f"[MAINTENANCE] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating maintenance request: {str(e)}")

@router.put("/maintenance/{request_id}")
async def update_maintenance_request(request_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
    """Update an existing maintenance request"""
    try:
        print(f"[MAINTENANCE] Updating request: {request_id}")
        
        # Check if request exists
        existing_requests = await db.select("maintenance_requests", filters={"id": request_id})
        if not existing_requests:
            raise HTTPException(status_code=404, detail="Maintenance request not found")
        
        # Update timestamp
        update_data["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        
        # Update in database
        try:
            await db.update("maintenance_requests", update_data, {"id": request_id})
            print(f"[MAINTENANCE] Request updated successfully: {request_id}")
            
            # Return updated request
            updated_requests = await db.select("maintenance_requests", filters={"id": request_id})
            return updated_requests[0] if updated_requests else {}
            
        except Exception as update_error:
            print(f"[MAINTENANCE] Database update failed: {update_error}")
            raise HTTPException(status_code=500, detail=f"Failed to update maintenance request: {str(update_error)}")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[MAINTENANCE] Update request error: {e}")
        print(f"[MAINTENANCE] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error updating maintenance request: {str(e)}")

@router.delete("/maintenance/{request_id}")
async def delete_maintenance_request(request_id: str) -> Dict[str, Any]:
    """Delete a maintenance request"""
    try:
        print(f"[MAINTENANCE] Deleting request: {request_id}")
        
        # Check if request exists
        existing_requests = await db.select("maintenance_requests", filters={"id": request_id})
        if not existing_requests:
            raise HTTPException(status_code=404, detail="Maintenance request not found")
        
        # Delete from database
        try:
            await db.delete("maintenance_requests", {"id": request_id})
            print(f"[MAINTENANCE] Request deleted successfully: {request_id}")
            
            return {"message": "Maintenance request deleted successfully"}
            
        except Exception as delete_error:
            print(f"[MAINTENANCE] Database delete failed: {delete_error}")
            raise HTTPException(status_code=500, detail=f"Failed to delete maintenance request: {str(delete_error)}")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[MAINTENANCE] Delete request error: {e}")
        print(f"[MAINTENANCE] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error deleting maintenance request: {str(e)}")

@router.get("/maintenance/{request_id}")
async def get_maintenance_request(request_id: str) -> Dict[str, Any]:
    """Get a specific maintenance request by ID"""
    try:
        print(f"[MAINTENANCE] Getting request: {request_id}")
        
        # Fetch from database
        requests = await db.select("maintenance_requests", filters={"id": request_id})
        if not requests:
            raise HTTPException(status_code=404, detail="Maintenance request not found")
        
        request_data = requests[0]
        print(f"[MAINTENANCE] Request found: {request_data.get('title', 'Unknown')}")
        
        return request_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[MAINTENANCE] Get request error: {e}")
        print(f"[MAINTENANCE] Full traceback:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error fetching maintenance request: {str(e)}")
