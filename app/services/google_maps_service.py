"""
Google Maps Service
Handles accurate location data using Google Maps APIs
"""

import requests
import datetime as dt
from typing import Dict, List, Optional, Any, Tuple
from ..core.config import settings


class GoogleMapsService:
    """Service for handling location data using Google Maps APIs"""
    
    BASE_URL = "https://maps.googleapis.com/maps/api"
    
    @staticmethod
    def _get_api_key() -> str:
        """Get Google Maps API key from settings"""
        api_key = settings.GOOGLE_MAPS_API_KEY
        if not api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY is not configured. Please set it in environment variables.")
        return api_key
    
    @staticmethod
    def geocode_from_pincode(pincode: str, country: str = "IN") -> Optional[Dict[str, Any]]:
        """
        Geocode a pincode using Google Maps Geocoding API
        Returns location data including coordinates, address components, etc.
        """
        try:
            api_key = GoogleMapsService._get_api_key()
            
            # Search for pincode in India
            query = f"{pincode}, India"
            
            url = f"{GoogleMapsService.BASE_URL}/geocode/json"
            params = {
                "address": query,
                "key": api_key,
                "region": "in",  # Bias results to India
                "components": f"country:{country}"
            }
            
            print(f"[GOOGLE_MAPS] Geocoding pincode: {pincode}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK" and data.get("results"):
                    result = data["results"][0]  # Get first result
                    
                    # Extract coordinates
                    location = result.get("geometry", {}).get("location", {})
                    lat = location.get("lat")
                    lng = location.get("lng")
                    
                    # Extract address components
                    address_components = result.get("address_components", [])
                    
                    # Parse address components
                    location_data = {
                        "pincode": pincode,
                        "latitude": lat,
                        "longitude": lng,
                        "formatted_address": result.get("formatted_address", ""),
                        "address_components": {}
                    }
                    
                    # Extract structured data from address components
                    for component in address_components:
                        types = component.get("types", [])
                        long_name = component.get("long_name", "")
                        short_name = component.get("short_name", "")
                        
                        if "postal_code" in types:
                            location_data["address_components"]["postal_code"] = long_name
                        if "locality" in types or "sublocality" in types:
                            location_data["address_components"]["city"] = long_name
                        if "administrative_area_level_2" in types:
                            location_data["address_components"]["district"] = long_name
                        if "administrative_area_level_1" in types:
                            location_data["address_components"]["state"] = long_name
                        if "country" in types:
                            location_data["address_components"]["country"] = long_name
                    
                    # Map to our format
                    location_data["state"] = location_data["address_components"].get("state", "")
                    location_data["district"] = location_data["address_components"].get("district", "")
                    location_data["city"] = location_data["address_components"].get("city", "")
                    location_data["country"] = location_data["address_components"].get("country", "India")
                    
                    print(f"[GOOGLE_MAPS] Successfully geocoded pincode {pincode}: {location_data.get('city')}, {location_data.get('state')}")
                    return location_data
                else:
                    print(f"[GOOGLE_MAPS] Geocoding failed for pincode {pincode}: {data.get('status')}")
                    return None
            else:
                print(f"[GOOGLE_MAPS] API request failed with status {response.status_code}")
                return None
                
        except ValueError as e:
            print(f"[GOOGLE_MAPS] Configuration error: {e}")
            return None
        except Exception as e:
            print(f"[GOOGLE_MAPS] Error geocoding pincode {pincode}: {e}")
            return None
    
    @staticmethod
    def reverse_geocode(lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """
        Reverse geocode coordinates to get address information
        """
        try:
            api_key = GoogleMapsService._get_api_key()
            
            url = f"{GoogleMapsService.BASE_URL}/geocode/json"
            params = {
                "latlng": f"{lat},{lng}",
                "key": api_key,
                "region": "in"
            }
            
            print(f"[GOOGLE_MAPS] Reverse geocoding coordinates: {lat}, {lng}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK" and data.get("results"):
                    result = data["results"][0]
                    
                    # Extract address components
                    address_components = result.get("address_components", [])
                    
                    location_data = {
                        "latitude": lat,
                        "longitude": lng,
                        "formatted_address": result.get("formatted_address", ""),
                        "address_components": {}
                    }
                    
                    # Parse address components
                    for component in address_components:
                        types = component.get("types", [])
                        long_name = component.get("long_name", "")
                        
                        if "postal_code" in types:
                            location_data["address_components"]["postal_code"] = long_name
                            location_data["pincode"] = long_name
                        if "locality" in types or "sublocality" in types:
                            location_data["address_components"]["city"] = long_name
                            location_data["city"] = long_name
                        if "administrative_area_level_2" in types:
                            location_data["address_components"]["district"] = long_name
                            location_data["district"] = long_name
                        if "administrative_area_level_1" in types:
                            location_data["address_components"]["state"] = long_name
                            location_data["state"] = long_name
                        if "country" in types:
                            location_data["address_components"]["country"] = long_name
                            location_data["country"] = long_name
                    
                    print(f"[GOOGLE_MAPS] Successfully reverse geocoded: {location_data.get('formatted_address')}")
                    return location_data
                else:
                    print(f"[GOOGLE_MAPS] Reverse geocoding failed: {data.get('status')}")
                    return None
            else:
                print(f"[GOOGLE_MAPS] API request failed with status {response.status_code}")
                return None
                
        except ValueError as e:
            print(f"[GOOGLE_MAPS] Configuration error: {e}")
            return None
        except Exception as e:
            print(f"[GOOGLE_MAPS] Error reverse geocoding: {e}")
            return None
    
    @staticmethod
    def geocode_address(address: str, country: str = "IN") -> Optional[Dict[str, Any]]:
        """
        Geocode an address string using Google Maps Geocoding API
        """
        try:
            api_key = GoogleMapsService._get_api_key()
            
            url = f"{GoogleMapsService.BASE_URL}/geocode/json"
            params = {
                "address": address,
                "key": api_key,
                "region": "in",
                "components": f"country:{country}"
            }
            
            print(f"[GOOGLE_MAPS] Geocoding address: {address}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK" and data.get("results"):
                    result = data["results"][0]
                    
                    location = result.get("geometry", {}).get("location", {})
                    lat = location.get("lat")
                    lng = location.get("lng")
                    
                    address_components = result.get("address_components", [])
                    
                    location_data = {
                        "latitude": lat,
                        "longitude": lng,
                        "formatted_address": result.get("formatted_address", ""),
                        "address": address
                    }
                    
                    # Parse address components
                    for component in address_components:
                        types = component.get("types", [])
                        long_name = component.get("long_name", "")
                        
                        if "postal_code" in types:
                            location_data["pincode"] = long_name
                        if "locality" in types or "sublocality" in types:
                            location_data["city"] = long_name
                        if "administrative_area_level_2" in types:
                            location_data["district"] = long_name
                        if "administrative_area_level_1" in types:
                            location_data["state"] = long_name
                        if "country" in types:
                            location_data["country"] = long_name
                    
                    print(f"[GOOGLE_MAPS] Successfully geocoded address: {location_data.get('formatted_address')}")
                    return location_data
                else:
                    print(f"[GOOGLE_MAPS] Geocoding failed: {data.get('status')}")
                    return None
            else:
                print(f"[GOOGLE_MAPS] API request failed with status {response.status_code}")
                return None
                
        except ValueError as e:
            print(f"[GOOGLE_MAPS] Configuration error: {e}")
            return None
        except Exception as e:
            print(f"[GOOGLE_MAPS] Error geocoding address: {e}")
            return None
    
    @staticmethod
    def get_place_autocomplete(input_text: str, country: str = "in") -> List[Dict[str, Any]]:
        """
        Get place autocomplete suggestions using Google Places API
        """
        try:
            api_key = GoogleMapsService._get_api_key()
            
            url = f"{GoogleMapsService.BASE_URL}/place/autocomplete/json"
            params = {
                "input": input_text,
                "key": api_key,
                "components": f"country:{country}",
                "types": "geocode"  # Restrict to addresses
            }
            
            print(f"[GOOGLE_MAPS] Getting autocomplete for: {input_text}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK":
                    predictions = data.get("predictions", [])
                    
                    results = []
                    for prediction in predictions:
                        results.append({
                            "place_id": prediction.get("place_id"),
                            "description": prediction.get("description", ""),
                            "structured_formatting": prediction.get("structured_formatting", {})
                        })
                    
                    print(f"[GOOGLE_MAPS] Found {len(results)} autocomplete suggestions")
                    return results
                else:
                    print(f"[GOOGLE_MAPS] Autocomplete failed: {data.get('status')}")
                    return []
            else:
                print(f"[GOOGLE_MAPS] API request failed with status {response.status_code}")
                return []
                
        except ValueError as e:
            print(f"[GOOGLE_MAPS] Configuration error: {e}")
            return []
        except Exception as e:
            print(f"[GOOGLE_MAPS] Error getting autocomplete: {e}")
            return []
    
    @staticmethod
    def get_place_details(place_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a place using Google Places API
        """
        try:
            api_key = GoogleMapsService._get_api_key()
            
            url = f"{GoogleMapsService.BASE_URL}/place/details/json"
            params = {
                "place_id": place_id,
                "key": api_key,
                "fields": "geometry,address_components,formatted_address,name,place_id"
            }
            
            print(f"[GOOGLE_MAPS] Getting place details for: {place_id}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("status") == "OK":
                    result = data.get("result", {})
                    
                    location = result.get("geometry", {}).get("location", {})
                    lat = location.get("lat")
                    lng = location.get("lng")
                    
                    address_components = result.get("address_components", [])
                    
                    place_data = {
                        "place_id": place_id,
                        "name": result.get("name", ""),
                        "formatted_address": result.get("formatted_address", ""),
                        "latitude": lat,
                        "longitude": lng
                    }
                    
                    # Parse address components
                    for component in address_components:
                        types = component.get("types", [])
                        long_name = component.get("long_name", "")
                        
                        if "postal_code" in types:
                            place_data["pincode"] = long_name
                        if "locality" in types or "sublocality" in types:
                            place_data["city"] = long_name
                        if "administrative_area_level_2" in types:
                            place_data["district"] = long_name
                        if "administrative_area_level_1" in types:
                            place_data["state"] = long_name
                        if "country" in types:
                            place_data["country"] = long_name
                    
                    print(f"[GOOGLE_MAPS] Successfully got place details: {place_data.get('formatted_address')}")
                    return place_data
                else:
                    print(f"[GOOGLE_MAPS] Place details failed: {data.get('status')}")
                    return None
            else:
                print(f"[GOOGLE_MAPS] API request failed with status {response.status_code}")
                return None
                
        except ValueError as e:
            print(f"[GOOGLE_MAPS] Configuration error: {e}")
            return None
        except Exception as e:
            print(f"[GOOGLE_MAPS] Error getting place details: {e}")
            return None

