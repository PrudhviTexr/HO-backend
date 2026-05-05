#!/usr/bin/env python3
"""
Pincode Data Import Script
Imports comprehensive Indian pincode data from reliable sources and stores in database
"""

import asyncio
import sys
import os
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import csv

# Add the app directory to Python path
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

async def import_pincode_from_api(pincode: str, db) -> Optional[Dict]:
    """
    Import pincode data from api.postalpincode.in (free, reliable Indian postal API)
    """
    try:
        print(f"  📍 Fetching data for pincode: {pincode}")
        
        response = requests.get(
            f"https://api.postalpincode.in/pincode/{pincode}",
            timeout=15,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data and len(data) > 0 and data[0].get('Status') == 'Success':
                post_office = data[0]['PostOffice'][0]
                
                # Get coordinates using Google Maps or fallback
                coordinates = await get_coordinates_for_pincode(pincode, post_office)
                
                pincode_data = {
                    'pincode': pincode,
                    'city': post_office.get('Name', ''),
                    'district': post_office.get('District', ''),
                    'state': post_office.get('State', ''),
                    'country': post_office.get('Country', 'India'),
                    'region': post_office.get('Region', ''),
                    'division': post_office.get('Division', ''),
                    'circle': post_office.get('Circle', ''),
                    'block': post_office.get('Block', ''),
                    'latitude': coordinates[0] if coordinates else None,
                    'longitude': coordinates[1] if coordinates else None
                }
                
                return pincode_data
        else:
            print(f"  ⚠️ API returned status {response.status_code} for pincode {pincode}")
            return None
            
    except Exception as e:
        print(f"  ❌ Error fetching pincode {pincode}: {e}")
        return None

async def get_coordinates_for_pincode(pincode: str, post_office: Dict) -> Optional[Tuple[float, float]]:
    """
    Get coordinates for pincode using Google Maps or fallback methods
    """
    try:
        # Try Google Maps first if available
        from app.services.google_maps_service import GoogleMapsService
        
        google_data = GoogleMapsService.geocode_from_pincode(pincode)
        if google_data and google_data.get("latitude") and google_data.get("longitude"):
            return (float(google_data["latitude"]), float(google_data["longitude"]))
    except Exception as e:
        print(f"    ⚠️ Google Maps not available: {e}")
    
    # Fallback: Use city and state to get coordinates
    try:
        city = post_office.get('District', '')
        state = post_office.get('State', '')
        
        if city and state:
            query = f"{city}, {state}, India"
            response = requests.get(
                f"https://nominatim.openstreetmap.org/search",
                params={
                    'q': query,
                    'format': 'json',
                    'limit': 1
                },
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    return (float(data[0]['lat']), float(data[0]['lon']))
    except Exception as e:
        print(f"    ⚠️ Fallback geocoding failed: {e}")
    
    return None

async def import_pincodes_from_list(pincodes: List[str], db, batch_size: int = 50):
    """
    Import multiple pincodes from a list
    """
    total = len(pincodes)
    imported = 0
    failed = 0
    skipped = 0
    
    print(f"\n🚀 Starting import of {total} pincodes...")
    print(f"📦 Batch size: {batch_size}\n")
    
    for i, pincode in enumerate(pincodes, 1):
        try:
            # Check if pincode already exists
            existing = await db.select("pincodes", filters={"pincode": pincode})
            if existing and len(existing) > 0:
                print(f"  ⏭️  [{i}/{total}] Pincode {pincode} already exists, skipping...")
                skipped += 1
                continue
            
            # Fetch pincode data
            pincode_data = await import_pincode_from_api(pincode, db)
            
            if pincode_data:
                # Insert into database
                await db.insert("pincodes", pincode_data)
                imported += 1
                print(f"  ✅ [{i}/{total}] Imported pincode {pincode}: {pincode_data.get('city')}, {pincode_data.get('state')}")
            else:
                failed += 1
                print(f"  ❌ [{i}/{total}] Failed to import pincode {pincode}")
            
            # Rate limiting - be nice to the API
            if i % batch_size == 0:
                print(f"\n⏸️  Pausing for 2 seconds after {i} pincodes...\n")
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(0.5)  # Small delay between requests
                
        except Exception as e:
            failed += 1
            print(f"  ❌ [{i}/{total}] Error importing pincode {pincode}: {e}")
    
    print(f"\n{'='*60}")
    print(f"📊 Import Summary:")
    print(f"  ✅ Successfully imported: {imported}")
    print(f"  ⏭️  Skipped (already exists): {skipped}")
    print(f"  ❌ Failed: {failed}")
    print(f"  📦 Total processed: {total}")
    print(f"{'='*60}\n")

async def import_pincodes_from_csv(csv_file_path: str, db):
    """
    Import pincodes from a CSV file
    Expected CSV format: pincode,city,district,state,latitude,longitude
    """
    pincodes = []
    
    try:
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                pincode = row.get('pincode', '').strip()
                if pincode and len(pincode) == 6 and pincode.isdigit():
                    pincodes.append(pincode)
        
        print(f"📄 Found {len(pincodes)} pincodes in CSV file")
        await import_pincodes_from_list(pincodes, db)
        
    except FileNotFoundError:
        print(f"❌ CSV file not found: {csv_file_path}")
    except Exception as e:
        print(f"❌ Error reading CSV file: {e}")

async def import_pincodes_by_range(start: int, end: int, db, step: int = 1):
    """
    Import pincodes in a range (useful for testing or specific regions)
    Example: import_pincodes_by_range(500000, 500099) for Hyderabad pincodes
    """
    pincodes = [str(i).zfill(6) for i in range(start, end + 1, step)]
    print(f"📋 Generated {len(pincodes)} pincodes in range {start}-{end}")
    await import_pincodes_from_list(pincodes, db)

async def import_common_pincodes(db):
    """
    Import common/important pincodes for major cities
    """
    common_pincodes = [
        # Hyderabad, Telangana
        '500001', '500002', '500003', '500004', '500005', '500006', '500007', '500008',
        '500009', '500010', '500012', '500013', '500014', '500015', '500016', '500017',
        '500018', '500019', '500020', '500022', '500023', '500024', '500025', '500026',
        '500027', '500028', '500029', '500030', '500031', '500032', '500033', '500034',
        '500035', '500036', '500037', '500038', '500039', '500040', '500041', '500042',
        '500043', '500044', '500045', '500046', '500047', '500048', '500049', '500050',
        '500051', '500052', '500053', '500054', '500055', '500056', '500057', '500058',
        '500059', '500060', '500061', '500062', '500063', '500064', '500065', '500066',
        '500067', '500068', '500069', '500070', '500071', '500072', '500073', '500074',
        '500075', '500076', '500077', '500078', '500079', '500080', '500081', '500082',
        '500083', '500084', '500085', '500086', '500087', '500088', '500089', '500090',
        '500091', '500092', '500093', '500094', '500095', '500096', '500097', '500098',
        '500099', '500100',
        
        # Mumbai, Maharashtra
        '400001', '400002', '400003', '400004', '400005', '400006', '400007', '400008',
        '400009', '400010', '400011', '400012', '400013', '400014', '400015', '400016',
        '400017', '400018', '400019', '400020', '400021', '400022', '400023', '400024',
        '400025', '400026', '400027', '400028', '400029', '400030', '400031', '400032',
        '400033', '400034', '400035', '400036', '400037', '400038', '400039', '400040',
        '400041', '400042', '400043', '400044', '400045', '400046', '400047', '400048',
        '400049', '400050', '400051', '400052', '400053', '400054', '400055', '400056',
        '400057', '400058', '400059', '400060', '400061', '400062', '400063', '400064',
        '400065', '400066', '400067', '400068', '400069', '400070', '400071', '400072',
        '400073', '400074', '400075', '400076', '400077', '400078', '400079', '400080',
        '400081', '400082', '400083', '400084', '400085', '400086', '400087', '400088',
        '400089', '400090', '400091', '400092', '400093', '400094', '400095', '400096',
        '400097', '400098', '400099', '400100',
        
        # Delhi
        '110001', '110002', '110003', '110004', '110005', '110006', '110007', '110008',
        '110009', '110010', '110011', '110012', '110013', '110014', '110015', '110016',
        '110017', '110018', '110019', '110020', '110021', '110022', '110023', '110024',
        '110025', '110026', '110027', '110028', '110029', '110030', '110031', '110032',
        '110033', '110034', '110035', '110036', '110037', '110038', '110039', '110040',
        '110041', '110042', '110043', '110044', '110045', '110046', '110047', '110048',
        '110049', '110050', '110051', '110052', '110053', '110054', '110055', '110056',
        '110057', '110058', '110059', '110060', '110061', '110062', '110063', '110064',
        '110065', '110066', '110067', '110068', '110069', '110070', '110071', '110072',
        '110073', '110074', '110075', '110076', '110077', '110078', '110079', '110080',
        '110081', '110082', '110083', '110084', '110085', '110086', '110087', '110088',
        '110089', '110090', '110091', '110092', '110093', '110094', '110095', '110096',
        '110097', '110098', '110099', '110100',
        
        # Bangalore, Karnataka
        '560001', '560002', '560003', '560004', '560005', '560006', '560007', '560008',
        '560009', '560010', '560011', '560012', '560013', '560014', '560015', '560016',
        '560017', '560018', '560019', '560020', '560021', '560022', '560023', '560024',
        '560025', '560026', '560027', '560028', '560029', '560030', '560031', '560032',
        '560033', '560034', '560035', '560036', '560037', '560038', '560039', '560040',
        '560041', '560042', '560043', '560044', '560045', '560046', '560047', '560048',
        '560049', '560050', '560051', '560052', '560053', '560054', '560055', '560056',
        '560057', '560058', '560059', '560060', '560061', '560062', '560063', '560064',
        '560065', '560066', '560067', '560068', '560069', '560070', '560071', '560072',
        '560073', '560074', '560075', '560076', '560077', '560078', '560079', '560080',
        '560081', '560082', '560083', '560084', '560085', '560086', '560087', '560088',
        '560089', '560090', '560091', '560092', '560093', '560094', '560095', '560096',
        '560097', '560098', '560099', '560100',
        
        # Chennai, Tamil Nadu
        '600001', '600002', '600003', '600004', '600005', '600006', '600007', '600008',
        '600009', '600010', '600011', '600012', '600013', '600014', '600015', '600016',
        '600017', '600018', '600019', '600020', '600021', '600022', '600023', '600024',
        '600025', '600026', '600027', '600028', '600029', '600030', '600031', '600032',
        '600033', '600034', '600035', '600036', '600037', '600038', '600039', '600040',
        '600041', '600042', '600043', '600044', '600045', '600046', '600047', '600048',
        '600049', '600050', '600051', '600052', '600053', '600054', '600055', '600056',
        '600057', '600058', '600059', '600060', '600061', '600062', '600063', '600064',
        '600065', '600066', '600067', '600068', '600069', '600070', '600071', '600072',
        '600073', '600074', '600075', '600076', '600077', '600078', '600079', '600080',
        '600081', '600082', '600083', '600084', '600085', '600086', '600087', '600088',
        '600089', '600090', '600091', '600092', '600093', '600094', '600095', '600096',
        '600097', '600098', '600099', '600100',
        
        # Kolkata, West Bengal
        '700001', '700002', '700003', '700004', '700005', '700006', '700007', '700008',
        '700009', '700010', '700011', '700012', '700013', '700014', '700015', '700016',
        '700017', '700018', '700019', '700020', '700021', '700022', '700023', '700024',
        '700025', '700026', '700027', '700028', '700029', '700030', '700031', '700032',
        '700033', '700034', '700035', '700036', '700037', '700038', '700039', '700040',
        '700041', '700042', '700043', '700044', '700045', '700046', '700047', '700048',
        '700049', '700050', '700051', '700052', '700053', '700054', '700055', '700056',
        '700057', '700058', '700059', '700060', '700061', '700062', '700063', '700064',
        '700065', '700066', '700067', '700068', '700069', '700070', '700071', '700072',
        '700073', '700074', '700075', '700076', '700077', '700078', '700079', '700080',
        '700081', '700082', '700083', '700084', '700085', '700086', '700087', '700088',
        '700089', '700090', '700091', '700092', '700093', '700094', '700095', '700096',
        '700097', '700098', '700099', '700100',
    ]
    
    print(f"📋 Importing {len(common_pincodes)} common pincodes for major cities...")
    await import_pincodes_from_list(common_pincodes, db)

async def main():
    """
    Main function to run the import script
    """
    try:
        from app.db.supabase_client import db
        
        print("="*60)
        print("🇮🇳 Indian Pincode Data Import Script")
        print("="*60)
        print("\nThis script imports pincode data from reliable sources:")
        print("  • api.postalpincode.in (Free Indian Postal API)")
        print("  • Google Maps API (if configured, for coordinates)")
        print("  • OpenStreetMap (fallback for coordinates)")
        print("\nOptions:")
        print("  1. Import common pincodes (major cities)")
        print("  2. Import pincodes from CSV file")
        print("  3. Import pincodes in a range")
        print("  4. Import custom list of pincodes")
        print("\n" + "="*60 + "\n")
        
        # For now, let's import common pincodes
        # You can modify this to use different import methods
        choice = input("Enter choice (1-4) or press Enter for common pincodes: ").strip()
        
        if choice == "2":
            csv_path = input("Enter CSV file path: ").strip()
            await import_pincodes_from_csv(csv_path, db)
        elif choice == "3":
            start = int(input("Enter start pincode (e.g., 500000): ").strip())
            end = int(input("Enter end pincode (e.g., 500099): ").strip())
            await import_pincodes_by_range(start, end, db)
        elif choice == "4":
            pincodes_input = input("Enter pincodes separated by comma (e.g., 500001,500002,500003): ").strip()
            pincodes = [p.strip() for p in pincodes_input.split(',')]
            await import_pincodes_from_list(pincodes, db)
        else:
            # Default: Import common pincodes
            await import_common_pincodes(db)
        
        print("\n✅ Import process completed!")
        print("📊 You can now use these pincodes in your application.")
        
    except Exception as e:
        print(f"\n❌ Import failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

