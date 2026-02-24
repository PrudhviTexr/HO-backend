from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List, Dict, Any
from ..db.supabase_client import db
from ..core.security import require_api_key
import traceback

router = APIRouter()

@router.get("/states")
async def get_states(_=Depends(require_api_key)):
    """Get all states"""
    try:
        print("[LOCATIONS] Fetching states")
        states = await db.admin_select("states")
        if states and len(states) > 0:
            print(f"[LOCATIONS] Found {len(states)} states in database")
            return states
        else:
            print("[LOCATIONS] No states found in database, returning fallback states")
            # Return fallback states if database is empty
            return [
                {"id": "1", "name": "Andhra Pradesh"},
                {"id": "2", "name": "Telangana"},
                {"id": "3", "name": "Karnataka"},
                {"id": "4", "name": "Tamil Nadu"},
                {"id": "5", "name": "Maharashtra"},
                {"id": "6", "name": "Delhi"},
                {"id": "7", "name": "West Bengal"}
            ]
    except Exception as e:
        print(f"[LOCATIONS] Get states error: {e}")
        try:
            import traceback as tb
            print(f"[LOCATIONS] Traceback: {tb.format_exc()}")
        except: pass
        # Return fallback states if database query fails
        return [
            {"id": "1", "name": "Andhra Pradesh"},
            {"id": "2", "name": "Telangana"},
            {"id": "3", "name": "Karnataka"},
            {"id": "4", "name": "Tamil Nadu"},
            {"id": "5", "name": "Maharashtra"},
            {"id": "6", "name": "Delhi"},
            {"id": "7", "name": "West Bengal"}
        ]

@router.get("/districts")
async def get_districts(
    state_id: Optional[str] = Query(None),
    _=Depends(require_api_key)
):
    """Get districts for a specific state"""
    try:
        print(f"[LOCATIONS] Fetching districts for state: {state_id}")
        if state_id:
            districts = await db.admin_select("districts", filters={"state_id": state_id})
        else:
            districts = await db.admin_select("districts")
        return districts or []
    except Exception as e:
        print(f"[LOCATIONS] Get districts error: {e}")
        # Return fallback districts based on state
        fallback_districts = {
            "1": [{"id": "1", "name": "Visakhapatnam", "state_id": "1"}, {"id": "2", "name": "Vijayawada", "state_id": "1"}],
            "2": [{"id": "3", "name": "Hyderabad", "state_id": "2"}, {"id": "4", "name": "Warangal", "state_id": "2"}],
            "3": [{"id": "5", "name": "Bangalore", "state_id": "3"}, {"id": "6", "name": "Mysore", "state_id": "3"}],
            "4": [{"id": "7", "name": "Chennai", "state_id": "4"}, {"id": "8", "name": "Coimbatore", "state_id": "4"}],
            "5": [{"id": "9", "name": "Mumbai", "state_id": "5"}, {"id": "10", "name": "Pune", "state_id": "5"}],
            "6": [{"id": "11", "name": "Delhi", "state_id": "6"}],
            "7": [{"id": "12", "name": "Kolkata", "state_id": "7"}, {"id": "13", "name": "Howrah", "state_id": "7"}]
        }
        return fallback_districts.get(state_id, [])

@router.get("/mandals")
async def get_mandals(
    state_id: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    _=Depends(require_api_key)
):
    """Get mandals for a specific district"""
    try:
        print(f"[LOCATIONS] Fetching mandals for district: {district_id}")
        filters = {}
        if state_id:
            filters["state_id"] = state_id
        if district_id:
            filters["district_id"] = district_id
        
        mandals = await db.admin_select("mandals", filters=filters)
        return mandals or []
    except Exception as e:
        print(f"[LOCATIONS] Get mandals error: {e}")
        # Return fallback mandals based on district
        fallback_mandals = {
            "1": [{"id": "1", "name": "Visakhapatnam Mandal", "district_id": "1", "state_id": "1"}],
            "2": [{"id": "2", "name": "Vijayawada Mandal", "district_id": "2", "state_id": "1"}],
            "3": [{"id": "3", "name": "Hyderabad Mandal", "district_id": "3", "state_id": "2"}],
            "4": [{"id": "4", "name": "Warangal Mandal", "district_id": "4", "state_id": "2"}],
            "5": [{"id": "5", "name": "Bangalore Mandal", "district_id": "5", "state_id": "3"}],
            "6": [{"id": "6", "name": "Mysore Mandal", "district_id": "6", "state_id": "3"}],
            "7": [{"id": "7", "name": "Chennai Mandal", "district_id": "7", "state_id": "4"}],
            "8": [{"id": "8", "name": "Coimbatore Mandal", "district_id": "8", "state_id": "4"}],
            "9": [{"id": "9", "name": "Mumbai Mandal", "district_id": "9", "state_id": "5"}],
            "10": [{"id": "10", "name": "Pune Mandal", "district_id": "10", "state_id": "5"}],
            "11": [{"id": "11", "name": "Delhi Mandal", "district_id": "11", "state_id": "6"}],
            "12": [{"id": "12", "name": "Kolkata Mandal", "district_id": "12", "state_id": "7"}],
            "13": [{"id": "13", "name": "Howrah Mandal", "district_id": "13", "state_id": "7"}]
        }
        return fallback_mandals.get(district_id, [])

@router.get("/cities")
async def get_cities(
    mandal_id: Optional[str] = Query(None),
    district_id: Optional[str] = Query(None),
    state_id: Optional[str] = Query(None),
    _=Depends(require_api_key)
):
    """Get cities for a specific mandal"""
    try:
        print(f"[LOCATIONS] Fetching cities for mandal: {mandal_id}")
        filters = {}
        if mandal_id:
            filters["mandal_id"] = mandal_id
        if district_id:
            filters["district_id"] = district_id
        if state_id:
            filters["state_id"] = state_id
        
        cities = await db.admin_select("cities", filters=filters)
        return cities or []
    except Exception as e:
        print(f"[LOCATIONS] Get cities error: {e}")
        # Return fallback cities based on mandal
        fallback_cities = {
            "1": [{"id": "1", "name": "Visakhapatnam", "mandal_id": "1", "district_id": "1", "state_id": "1"}],
            "2": [{"id": "2", "name": "Vijayawada", "mandal_id": "2", "district_id": "2", "state_id": "1"}],
            "3": [{"id": "3", "name": "Hyderabad", "mandal_id": "3", "district_id": "3", "state_id": "2"}],
            "4": [{"id": "4", "name": "Warangal", "mandal_id": "4", "district_id": "4", "state_id": "2"}],
            "5": [{"id": "5", "name": "Bangalore", "mandal_id": "5", "district_id": "5", "state_id": "3"}],
            "6": [{"id": "6", "name": "Mysore", "mandal_id": "6", "district_id": "6", "state_id": "3"}],
            "7": [{"id": "7", "name": "Chennai", "mandal_id": "7", "district_id": "7", "state_id": "4"}],
            "8": [{"id": "8", "name": "Coimbatore", "mandal_id": "8", "district_id": "8", "state_id": "4"}],
            "9": [{"id": "9", "name": "Mumbai", "mandal_id": "9", "district_id": "9", "state_id": "5"}],
            "10": [{"id": "10", "name": "Pune", "mandal_id": "10", "district_id": "10", "state_id": "5"}],
            "11": [{"id": "11", "name": "Delhi", "mandal_id": "11", "district_id": "11", "state_id": "6"}],
            "12": [{"id": "12", "name": "Kolkata", "mandal_id": "12", "district_id": "12", "state_id": "7"}],
            "13": [{"id": "13", "name": "Howrah", "mandal_id": "13", "district_id": "13", "state_id": "7"}]
        }
        return fallback_cities.get(mandal_id, [])

@router.get("/coordinates")
async def get_coordinates_from_pincode(
    pincode: str = Query(..., description="Pincode to get coordinates for"),
    _=Depends(require_api_key)
):
    """Get coordinates (latitude, longitude) for a given pincode"""
    try:
        print(f"[LOCATIONS] Fetching coordinates for pincode: {pincode}")
        
        # Try to get coordinates from database first
        try:
            coordinates = await db.admin_select("pincodes", filters={"pincode": pincode})
            if coordinates and len(coordinates) > 0:
                coord = coordinates[0]
                return {
                    "lat": coord.get("latitude"),
                    "lng": coord.get("longitude"),
                    "pincode": pincode
                }
        except Exception as db_error:
            print(f"[LOCATIONS] Database query failed: {db_error}")
        
        # No hardcoded fallback coordinates - rely on database or external APIs only
        
        # If no coordinates found, return null
        return {"lat": None, "lng": None, "pincode": pincode}
        
    except Exception as e:
        print(f"[LOCATIONS] Get coordinates error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get coordinates: {str(e)}")

@router.post("/states")
async def create_state(state_data: dict, _=Depends(require_api_key)):
    """Create a new state"""
    try:
        print(f"[LOCATIONS] Creating state: {state_data}")
        state_id = await db.insert("states", state_data)
        return {"id": state_id, **state_data}
    except Exception as e:
        print(f"[LOCATIONS] Create state error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create state: {str(e)}")

@router.post("/districts")
async def create_district(district_data: dict, _=Depends(require_api_key)):
    """Create a new district"""
    try:
        print(f"[LOCATIONS] Creating district: {district_data}")
        district_id = await db.insert("districts", district_data)
        return {"id": district_id, **district_data}
    except Exception as e:
        print(f"[LOCATIONS] Create district error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create district: {str(e)}")

@router.post("/mandals")
async def create_mandal(mandal_data: dict, _=Depends(require_api_key)):
    """Create a new mandal"""
    try:
        print(f"[LOCATIONS] Creating mandal: {mandal_data}")
        mandal_id = await db.insert("mandals", mandal_data)
        return {"id": mandal_id, **mandal_data}
    except Exception as e:
        print(f"[LOCATIONS] Create mandal error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create mandal: {str(e)}")

@router.post("/cities")
async def create_city(city_data: dict, _=Depends(require_api_key)):
    """Create a new city"""
    try:
        print(f"[LOCATIONS] Creating city: {city_data}")
        city_id = await db.insert("cities", city_data)
        return {"id": city_id, **city_data}
    except Exception as e:
        print(f"[LOCATIONS] Create city error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create city: {str(e)}")
