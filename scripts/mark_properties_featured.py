"""
Script to mark properties as featured for testing
Run this to ensure you have featured properties in the database
"""
import asyncio
import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.supabase_client import db

async def mark_properties_as_featured():
    """Mark the first 8 active, verified properties as featured"""
    try:
        # Get all active, verified properties
        properties = await db.select(
            "properties",
            filters={"status": "active", "verified": True},
            limit=10,
            order_by="created_at",
            ascending=False
        )
        
        if not properties:
            print("No active, verified properties found in database")
            return
        
        print(f"Found {len(properties)} active, verified properties")
        
        # Mark first 8 as featured
        featured_count = 0
        for i, prop in enumerate(properties[:8]):
            property_id = prop.get('id')
            title = prop.get('title', 'N/A')
            
            # Update to featured=True
            await db.update(
                "properties",
                {"featured": True},
                {"id": property_id}
            )
            
            featured_count += 1
            print(f"{i+1}. Marked as FEATURED: {title} (ID: {property_id})")
        
        print(f"\n✅ Successfully marked {featured_count} properties as featured!")
        
        # Verify
        featured_props = await db.select(
            "properties",
            filters={"featured": True},
            limit=20
        )
        
        print(f"\n📊 Total featured properties in database: {len(featured_props)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(mark_properties_as_featured())

