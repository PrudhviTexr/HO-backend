"""
Admin service functions
"""
import uuid
from typing import Optional
from ..db.supabase_client import db

async def generate_custom_id(user_type: str) -> str:
    """Generate a custom ID for users based on their type"""
    try:
        # Get the current sequence for this user type
        sequences = await db.select("system_counters", filters={"id": f"{user_type}_sequence"})
        
        if sequences:
            current_sequence = sequences[0].get("current_value", 0)
        else:
            current_sequence = 0
        
        # Increment the sequence
        new_sequence = current_sequence + 1
        
        # Update or create the sequence record
        if sequences:
            await db.update("system_counters", 
                          {"current_value": new_sequence}, 
                          filters={"id": f"{user_type}_sequence"})
        else:
            await db.insert("system_counters", {
                "id": f"{user_type}_sequence",
                "current_value": new_sequence,
                "prefix": user_type.upper()
            })
        
        # Generate custom ID
        if user_type == "buyer":
            return f"BUY{new_sequence:06d}"
        elif user_type == "seller":
            return f"SEL{new_sequence:06d}"
        elif user_type == "agent":
            return f"AGT{new_sequence:06d}"
        else:
            return f"USR{new_sequence:06d}"
            
    except Exception as e:
        print(f"[ADMIN-SERVICE] Error generating custom ID: {e}")
        # Fallback to a simple UUID-based ID
        return f"{user_type.upper()}{str(uuid.uuid4())[:8].upper()}"

async def generate_property_custom_id() -> str:
    """Generate a custom ID for properties"""
    try:
        # Get the current sequence for properties
        sequences = await db.select("system_counters", filters={"id": "property_sequence"})
        
        if sequences:
            current_sequence = sequences[0].get("current_value", 0)
        else:
            current_sequence = 0
        
        # Increment the sequence
        new_sequence = current_sequence + 1
        
        # Update or create the sequence record
        if sequences:
            await db.update("system_counters", 
                          {"current_value": new_sequence}, 
                          filters={"id": "property_sequence"})
        else:
            await db.insert("system_counters", {
                "id": "property_sequence",
                "current_value": new_sequence,
                "prefix": "PROP"
            })
        
        # Generate custom ID for property: PROP000001, PROP000002, etc.
        return f"PROP{new_sequence:06d}"
            
    except Exception as e:
        print(f"[ADMIN-SERVICE] Error generating property custom ID: {e}")
        # Fallback to a simple UUID-based ID
        import time
        return f"PROP{int(time.time())%1000000:06d}"
