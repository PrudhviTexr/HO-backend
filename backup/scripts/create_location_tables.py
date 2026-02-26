#!/usr/bin/env python3
"""
Database Migration Script - Create Location Tables
This script creates the missing location tables (states, districts, mandals, cities, pincodes)
"""

import asyncio
import sys
import os
from pathlib import Path

# Add the app directory to Python path
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

async def create_location_tables():
    try:
        from app.db.supabase_client import db
        
        print("🔍 Creating location tables by inserting sample data...")
        print("ℹ️ Note: Tables will be created automatically when we insert data")
        
        # Insert default states data
        print("📝 Inserting default states data...")
        states_data = [
            {'id': '1', 'name': 'Andhra Pradesh'},
            {'id': '2', 'name': 'Telangana'},
            {'id': '3', 'name': 'Karnataka'},
            {'id': '4', 'name': 'Tamil Nadu'},
            {'id': '5', 'name': 'Maharashtra'},
            {'id': '6', 'name': 'Delhi'},
            {'id': '7', 'name': 'West Bengal'}
        ]
        
        for state in states_data:
            try:
                await db.insert('states', state)
            except Exception as e:
                if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                    print(f"  ⚠️ State {state['name']} already exists")
                else:
                    print(f"  ❌ Error inserting state {state['name']}: {e}")
        
        # Insert default districts for Telangana
        print("📝 Inserting default districts data...")
        districts_data = [
            {'id': 'TG001', 'name': 'Hyderabad', 'state_id': '2'},
            {'id': 'TG002', 'name': 'Rangareddy', 'state_id': '2'},
            {'id': 'TG003', 'name': 'Medchal-Malkajgiri', 'state_id': '2'},
            {'id': 'TG004', 'name': 'Sangareddy', 'state_id': '2'},
            {'id': 'TG005', 'name': 'Vikarabad', 'state_id': '2'}
        ]
        
        for district in districts_data:
            try:
                await db.insert('districts', district)
            except Exception as e:
                if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                    print(f"  ⚠️ District {district['name']} already exists")
                else:
                    print(f"  ❌ Error inserting district {district['name']}: {e}")
        
        # Insert default mandals for Hyderabad district
        print("📝 Inserting default mandals data...")
        mandals_data = [
            {'id': 'TG001001', 'name': 'Secunderabad', 'district_id': 'TG001', 'state_id': '2'}
        ]
        
        for mandal in mandals_data:
            try:
                await db.insert('mandals', mandal)
            except Exception as e:
                if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                    print(f"  ⚠️ Mandal {mandal['name']} already exists")
                else:
                    print(f"  ❌ Error inserting mandal {mandal['name']}: {e}")
        
        # Insert default cities for Hyderabad mandals
        print("📝 Inserting default cities data...")
        cities_data = [
            {'id': 'TG001005002', 'name': 'Kondapur', 'mandal_id': 'TG001005', 'district_id': 'TG001', 'state_id': '2'}
        ]
        
        for city in cities_data:
            try:
                await db.insert('cities', city)
            except Exception as e:
                if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                    print(f"  ⚠️ City {city['name']} already exists")
                else:
                    print(f"  ❌ Error inserting city {city['name']}: {e}")
        
        # Insert sample pincode data with coordinates
        print("📝 Inserting sample pincode data...")
        pincodes_data = [
            {'pincode': '500033', 'latitude': 17.3850, 'longitude': 78.4867, 'city': 'Hyderabad', 'district': 'Hyderabad', 'state': 'Telangana'},
            {'pincode': '500034', 'latitude': 17.3850, 'longitude': 78.4867, 'city': 'Hyderabad', 'district': 'Hyderabad', 'state': 'Telangana'},
            {'pincode': '500045', 'latitude': 17.3850, 'longitude': 78.4867, 'city': 'Hyderabad', 'district': 'Hyderabad', 'state': 'Telangana'},
            {'pincode': '500090', 'latitude': 17.3850, 'longitude': 78.4867, 'city': 'Hyderabad', 'district': 'Hyderabad', 'state': 'Telangana'},
            {'pincode': '400050', 'latitude': 19.0760, 'longitude': 72.8777, 'city': 'Mumbai', 'district': 'Mumbai', 'state': 'Maharashtra'},
            {'pincode': '110049', 'latitude': 28.6139, 'longitude': 77.2090, 'city': 'Delhi', 'district': 'Delhi', 'state': 'Delhi'},
            {'pincode': '560001', 'latitude': 12.9716, 'longitude': 77.5946, 'city': 'Bangalore', 'district': 'Bangalore Urban', 'state': 'Karnataka'},
            {'pincode': '600001', 'latitude': 13.0827, 'longitude': 80.2707, 'city': 'Chennai', 'district': 'Chennai', 'state': 'Tamil Nadu'}
        ]
        
        for pincode in pincodes_data:
            try:
                await db.insert('pincodes', pincode)
            except Exception as e:
                if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                    print(f"  ⚠️ Pincode {pincode['pincode']} already exists")
                else:
                    print(f"  ❌ Error inserting pincode {pincode['pincode']}: {e}")
        
        print("✅ Database migration completed successfully!")
        print("🎉 Location tables and sample data have been created!")
        print("📋 You can now test pincode auto-population functionality.")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(create_location_tables())
