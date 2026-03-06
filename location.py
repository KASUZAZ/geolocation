import requests
import json
import re
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
import logging
import threading
import concurrent.futures
from functools import lru_cache
import socket
import struct

# Try to import phonenumbers, but provide fallback if not available
try:
    import phonenumbers
    from phonenumbers import geocoder, carrier, timezone as phone_timezone
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False
    print("Warning: phonenumbers library not available. Some features may be limited.")


def get_location_info(ip_address: str) -> Optional[Dict[str, Any]]:
    """
    Get location information for a given IP address using ip-api.com
    
    Args:
        ip_address (str): The IP address to look up
        
    Returns:
        dict: Location information if successful, None if failed
    """
    try:
        response = requests.get(f'http://ip-api.com/json/{ip_address}')
        response.raise_for_status()  # Raise an exception for bad status codes
        
        data = response.json()
        
        if data.get('status') == 'success':
            return {
                'ip': data.get('query'),
                'country': data.get('country'),
                'region': data.get('regionName'),
                'city': data.get('city'),
                'latitude': data.get('lat'),
                'longitude': data.get('lon'),
                'isp': data.get('isp')
            }
        else:
            print(f"API Error: {data.get('message', 'Unknown error')}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Network Error: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {str(e)}")
        return None
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        return None


def display_location_info(location_data: Dict[str, Any]) -> None:
    """
    Display location information in a formatted way
    
    Args:
        location_data (dict): Location information dictionary
    """
    if not location_data:
        print("No location data to display")
        return
        
    print("\n" + "="*50)
    print("LOCATION INFORMATION")
    print("="*50)
    print(f"IP Address: {location_data['ip']}")
    print(f"Country: {location_data['country']}")
    print(f"Region: {location_data['region']}")
    print(f"City: {location_data['city']}")
    print(f"Coordinates: {location_data['latitude']}, {location_data['longitude']}")
    print(f"ISP: {location_data['isp']}")
    print("="*50 + "\n")


def validate_phone_number(phone_number: str) -> Optional[str]:
    """
    Validate and normalize phone number using phonenumbers library
    
    Args:
        phone_number (str): Raw phone number input
        
    Returns:
        str: Validated and normalized phone number or None if invalid
    """
    try:
        # Clean the phone number
        cleaned_number = re.sub(r'[^\d+]', '', phone_number)
        
        # Handle Malaysian numbers
        if cleaned_number.startswith('60'):
            cleaned_number = '0' + cleaned_number[2:]
        elif cleaned_number.startswith('+60'):
            cleaned_number = '0' + cleaned_number[3:]
        elif not cleaned_number.startswith('0'):
            cleaned_number = '0' + cleaned_number
            
        # Validate using phonenumbers library
        parsed_number = phonenumbers.parse(cleaned_number, 'MY')
        
        if phonenumbers.is_valid_number(parsed_number):
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        else:
            return None
            
    except Exception as e:
        logging.error(f"Phone validation error: {e}")
        return None


@lru_cache(maxsize=1000)
def get_advanced_phone_location(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Get advanced location information for a phone number using multiple data sources
    
    Args:
        phone_number (str): The phone number to look up
        
    Returns:
        dict: Advanced location information if successful, None if failed
    """
    try:
        # Validate phone number first
        validated_number = validate_phone_number(phone_number)
        if not validated_number:
            return None
            
        # Use phonenumbers library for basic info
        parsed_number = phonenumbers.parse(validated_number, 'MY')
        
        # Get location from phonenumbers
        location = geocoder.description_for_number(parsed_number, 'en')
        carrier_name = carrier.name_for_number(parsed_number, 'en')
        timezones = phone_timezone.time_zones_for_number(parsed_number)
        
        # Malaysia specific area codes mapping
        malaysia_area_codes = {
            '010': {'state': 'Selangor', 'city': 'Shah Alam', 'carrier': 'Celcom', 'districts': ['Klang Valley']},
            '011': {'state': 'Kuala Lumpur', 'city': 'Kuala Lumpur', 'carrier': 'Digi', 'districts': ['Kuala Lumpur']},
            '012': {'state': 'Johor', 'city': 'Johor Bahru', 'carrier': 'Celcom', 'districts': ['Johor Bahru', 'Skudai']},
            '013': {'state': 'Penang', 'city': 'George Town', 'carrier': 'Maxis', 'districts': ['Penang Island']},
            '014': {'state': 'Terengganu', 'city': 'Kuala Terengganu', 'carrier': 'Digi', 'districts': ['Kuala Terengganu', 'Kuala Nerus']},
            '015': {'state': 'Pahang', 'city': 'Kuantan', 'carrier': 'U Mobile', 'districts': ['Kuantan']},
            '016': {'state': 'Selangor', 'city': 'Petaling Jaya', 'carrier': 'Celcom', 'districts': ['Petaling', 'Klang']},
            '017': {'state': 'Kuala Lumpur', 'city': 'Kuala Lumpur', 'carrier': 'Maxis', 'districts': ['Kuala Lumpur']},
            '018': {'state': 'Johor', 'city': 'Johor Bahru', 'carrier': 'Digi', 'districts': ['Johor Bahru', 'Iskandar']},
            '019': {'state': 'Perak', 'city': 'Ipoh', 'carrier': 'U Mobile', 'districts': ['Ipoh', 'Kinta']},
        }
        
        prefix = validated_number[-10:-7]  # Get last 3 digits before number
        if prefix in malaysia_area_codes:
            area_info = malaysia_area_codes[prefix]
            
            # Get precise coordinates
            coordinates = get_precise_coordinates(area_info['city'], area_info['state'])
            
            return {
                'phone': validated_number,
                'original_input': phone_number,
                'country': 'Malaysia',
                'country_code': '+60',
                'state': area_info['state'],
                'city': area_info['city'],
                'districts': area_info['districts'],
                'carrier': area_info['carrier'],
                'line_type': 'Mobile',
                'valid': True,
                'location_details': f"{area_info['city']}, {area_info['state']}, Malaysia",
                'coordinates': coordinates,
                'timezone': timezones[0] if timezones else 'Asia/Kuala_Lumpur',
                'phonenumbers_location': location,
                'phonenumbers_carrier': carrier_name,
                'lookup_timestamp': datetime.now().isoformat(),
                'confidence_score': 0.95
            }
        
        # Fallback for unknown prefixes
        return {
            'phone': validated_number,
            'original_input': phone_number,
            'country': 'Malaysia',
            'country_code': '+60',
            'state': 'Unknown',
            'city': 'Unknown',
            'districts': [],
            'carrier': 'Unknown',
            'line_type': 'Mobile',
            'valid': True,
            'location_details': 'Location information not available for this prefix',
            'coordinates': None,
            'timezone': 'Asia/Kuala_Lumpur',
            'phonenumbers_location': location,
            'phonenumbers_carrier': carrier_name,
            'lookup_timestamp': datetime.now().isoformat(),
            'confidence_score': 0.5
        }
            
    except Exception as e:
        logging.error(f"Advanced phone lookup error: {e}")
        return None


def get_precise_coordinates(city: str, state: str) -> Optional[Dict[str, float]]:
    """
    Get precise coordinates for a city/state in Malaysia with enhanced data
    
    Args:
        city (str): City name
        state (str): State name
        
    Returns:
        dict: Precise coordinates if found, None otherwise
    """
    # Enhanced coordinate database with more precise locations
    malaysia_coordinates = {
        # Major cities
        'Kuala Lumpur': {'lat': 3.139001, 'lon': 101.686855, 'accuracy': 'city_center'},
        'Shah Alam': {'lat': 3.073791, 'lon': 101.518005, 'accuracy': 'city_center'},
        'Petaling Jaya': {'lat': 3.111712, 'lon': 101.641716, 'accuracy': 'city_center'},
        'Ipoh': {'lat': 4.592928, 'lon': 101.083710, 'accuracy': 'city_center'},
        'Johor Bahru': {'lat': 1.466667, 'lon': 103.750000, 'accuracy': 'city_center'},
        'George Town': {'lat': 5.414922, 'lon': 100.328679, 'accuracy': 'city_center'},
        'Kuching': {'lat': 1.553200, 'lon': 110.340000, 'accuracy': 'city_center'},
        'Kota Kinabalu': {'lat': 5.973700, 'lon': 116.071000, 'accuracy': 'city_center'},
        'Kuala Terengganu': {'lat': 5.330900, 'lon': 103.134400, 'accuracy': 'city_center'},
        'Kuantan': {'lat': 3.812000, 'lon': 103.323000, 'accuracy': 'city_center'},
        
        # Districts and towns
        'Klang': {'lat': 3.038600, 'lon': 101.447000, 'accuracy': 'city_center'},
        'Subang Jaya': {'lat': 3.057000, 'lon': 101.586000, 'accuracy': 'city_center'},
        'Ampang': {'lat': 3.120000, 'lon': 101.720000, 'accuracy': 'city_center'},
        'Cheras': {'lat': 3.090000, 'lon': 101.710000, 'accuracy': 'city_center'},
        'Kepong': {'lat': 3.200000, 'lon': 101.630000, 'accuracy': 'city_center'},
        'Setapak': {'lat': 3.200000, 'lon': 101.680000, 'accuracy': 'city_center'},
        'Rawang': {'lat': 3.350000, 'lon': 101.550000, 'accuracy': 'city_center'},
        'Selayang': {'lat': 3.260000, 'lon': 101.620000, 'accuracy': 'city_center'},
        'Batu Caves': {'lat': 3.260000, 'lon': 101.650000, 'accuracy': 'landmark'},
        'Puchong': {'lat': 3.010000, 'lon': 101.580000, 'accuracy': 'city_center'},
        'Balakong': {'lat': 3.000000, 'lon': 101.680000, 'accuracy': 'city_center'},
        'Bangi': {'lat': 2.920000, 'lon': 101.740000, 'accuracy': 'city_center'},
        'Kajang': {'lat': 2.990000, 'lon': 101.780000, 'accuracy': 'city_center'},
        'Seremban': {'lat': 2.720000, 'lon': 101.940000, 'accuracy': 'city_center'},
        'Melaka': {'lat': 2.200000, 'lon': 102.250000, 'accuracy': 'city_center'},
        'Alor Setar': {'lat': 6.120000, 'lon': 100.370000, 'accuracy': 'city_center'},
        'Kota Bharu': {'lat': 6.130000, 'lon': 102.250000, 'accuracy': 'city_center'},
        'Kuala Kangsar': {'lat': 4.960000, 'lon': 100.910000, 'accuracy': 'city_center'},
        'Taiping': {'lat': 4.850000, 'lon': 100.740000, 'accuracy': 'city_center'},
        'Sungai Petani': {'lat': 5.650000, 'lon': 100.500000, 'accuracy': 'city_center'},
        'Butterworth': {'lat': 5.430000, 'lon': 100.380000, 'accuracy': 'city_center'},
        'Seberang Jaya': {'lat': 5.380000, 'lon': 100.420000, 'accuracy': 'city_center'},
        'Nibong Tebal': {'lat': 5.220000, 'lon': 100.470000, 'accuracy': 'city_center'},
        'Batu Pahat': {'lat': 1.840000, 'lon': 102.920000, 'accuracy': 'city_center'},
        'Muar': {'lat': 2.040000, 'lon': 102.560000, 'accuracy': 'city_center'},
        'Segamat': {'lat': 2.440000, 'lon': 103.010000, 'accuracy': 'city_center'},
        'Kluang': {'lat': 2.020000, 'lon': 103.320000, 'accuracy': 'city_center'},
        'Mersing': {'lat': 2.440000, 'lon': 103.840000, 'accuracy': 'city_center'},
        'Kuantan': {'lat': 3.812000, 'lon': 103.323000, 'accuracy': 'city_center'},
        'Temerloh': {'lat': 3.440000, 'lon': 102.420000, 'accuracy': 'city_center'},
        'Jerantut': {'lat': 3.950000, 'lon': 102.330000, 'accuracy': 'city_center'},
        'Kuala Lipis': {'lat': 4.070000, 'lon': 101.820000, 'accuracy': 'city_center'},
        'Kota Bharu': {'lat': 6.130000, 'lon': 102.250000, 'accuracy': 'city_center'},
        'Kubang Kerian': {'lat': 6.080000, 'lon': 102.260000, 'accuracy': 'city_center'},
        'Pasir Mas': {'lat': 6.020000, 'lon': 102.150000, 'accuracy': 'city_center'},
        'Tumpat': {'lat': 6.120000, 'lon': 102.120000, 'accuracy': 'city_center'},
        'Kuala Terengganu': {'lat': 5.330900, 'lon': 103.134400, 'accuracy': 'city_center'},
        'Kuala Nerus': {'lat': 5.380000, 'lon': 103.120000, 'accuracy': 'city_center'},
        'Kemaman': {'lat': 4.730000, 'lon': 103.430000, 'accuracy': 'city_center'},
        'Dungun': {'lat': 4.790000, 'lon': 103.480000, 'accuracy': 'city_center'},
        'Marang': {'lat': 5.150000, 'lon': 103.000000, 'accuracy': 'city_center'},
        'Kota Kinabalu': {'lat': 5.973700, 'lon': 116.071000, 'accuracy': 'city_center'},
        'Sandakan': {'lat': 5.840000, 'lon': 118.120000, 'accuracy': 'city_center'},
        'Tawau': {'lat': 4.240000, 'lon': 117.890000, 'accuracy': 'city_center'},
        'Keningau': {'lat': 5.330000, 'lon': 115.960000, 'accuracy': 'city_center'},
        'Kudat': {'lat': 7.080000, 'lon': 116.840000, 'accuracy': 'city_center'},
        'Kuching': {'lat': 1.553200, 'lon': 110.340000, 'accuracy': 'city_center'},
        'Sibu': {'lat': 2.290000, 'lon': 111.820000, 'accuracy': 'city_center'},
        'Miri': {'lat': 4.410000, 'lon': 113.990000, 'accuracy': 'city_center'},
        'Bintulu': {'lat': 3.140000, 'lon': 113.030000, 'accuracy': 'city_center'},
        'Sarikei': {'lat': 2.000000, 'lon': 111.480000, 'accuracy': 'city_center'},
    }
    
    # Try exact match first
    if city in malaysia_coordinates:
        return malaysia_coordinates[city]
    
    # Try partial match
    for key, coords in malaysia_coordinates.items():
        if city.lower() in key.lower() or key.lower() in city.lower():
            return coords
    
    return None


def get_coordinates_for_city(city: str, state: str) -> Optional[Dict[str, float]]:
    """
    Get approximate coordinates for a city/state in Malaysia
    
    Args:
        city (str): City name
        state (str): State name
        
    Returns:
        dict: Coordinates if found, None otherwise
    """
    malaysia_coordinates = {
        'Kuala Lumpur': {'lat': 3.1390, 'lon': 101.6869},
        'Shah Alam': {'lat': 3.0738, 'lon': 101.5183},
        'Petaling Jaya': {'lat': 3.1117, 'lon': 101.6417},
        'Ipoh': {'lat': 4.5929, 'lon': 101.0833},
        'Johor Bahru': {'lat': 1.4667, 'lon': 103.7500},
        'George Town': {'lat': 5.4149, 'lon': 100.3286},
        'Kuching': {'lat': 1.5532, 'lon': 110.3400},
        'Kota Kinabalu': {'lat': 5.9737, 'lon': 116.0710},
        'Kuala Terengganu': {'lat': 5.3309, 'lon': 103.1344},
    }
    
    # Try exact match first
    if city in malaysia_coordinates:
        return malaysia_coordinates[city]
    
    # Try partial match
    for key, coords in malaysia_coordinates.items():
        if city.lower() in key.lower() or key.lower() in city.lower():
            return coords
    
    return None


def display_advanced_phone_info(phone_data: Dict[str, Any]) -> None:
    """
    Display advanced phone number information in a formatted way
    
    Args:
        phone_data (dict): Advanced phone number information dictionary
    """
    if not phone_data:
        print("No phone data to display")
        return
        
    print("\n" + "="*80)
    print("ADVANCED PHONE NUMBER INFORMATION")
    print("="*80)
    print(f"Phone Number: {phone_data['phone']}")
    print(f"Original Input: {phone_data['original_input']}")
    print(f"Country: {phone_data['country']} ({phone_data.get('country_code', '')})")
    print(f"State/Province: {phone_data['state']}")
    print(f"City: {phone_data['city']}")
    print(f"Districts: {', '.join(phone_data.get('districts', [])) if phone_data.get('districts') else 'N/A'}")
    print(f"Carrier: {phone_data['carrier']}")
    print(f"Line Type: {phone_data['line_type']}")
    print(f"Location Details: {phone_data['location_details']}")
    
    if phone_data.get('coordinates'):
        coords = phone_data['coordinates']
        print(f"GPS Coordinates: {coords['lat']}, {coords['lon']}")
        print(f"Coordinate Accuracy: {coords.get('accuracy', 'Unknown')}")
        print(f"Google Maps: https://maps.google.com/?q={coords['lat']},{coords['lon']}")
    
    print(f"Timezone: {phone_data.get('timezone', 'Unknown')}")
    print(f"Phonenumbers Location: {phone_data.get('phonenumbers_location', 'Unknown')}")
    print(f"Phonenumbers Carrier: {phone_data.get('phonenumbers_carrier', 'Unknown')}")
    print(f"Lookup Timestamp: {phone_data.get('lookup_timestamp', 'Unknown')}")
    print(f"Confidence Score: {phone_data.get('confidence_score', 0) * 100:.1f}%")
    print(f"Number Valid: {'Yes' if phone_data['valid'] else 'No'}")
    print("="*80 + "\n")


def main():
    """Main function to run the location lookup tool"""
    print("Location Lookup Tool")
    print("-" * 30)
    print("1. IP Address Lookup")
    print("2. Phone Number Lookup")
    print("Type 'quit' to exit")
    print("-" * 30)
    
    while True:
        try:
            choice = input("\nSelect lookup type (1-IP, 2-Phone): ").strip()
            
            if choice.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
                
            if choice == '1':
                ip = input("Enter IP address: ").strip()
                if not ip:
                    print("Please enter a valid IP address")
                    continue
                    
                print(f"Looking up information for: {ip}")
                location_data = get_location_info(ip)
                
                if location_data:
                    display_location_info(location_data)
                else:
                    print("Failed to retrieve location information\n")
                    
            elif choice == '2':
                phone = input("Enter phone number: ").strip()
                if not phone:
                    print("Please enter a valid phone number")
                    continue
                    
                print(f"Looking up information for: {phone}")
                phone_data = get_advanced_phone_location(phone)
                
                if phone_data:
                    display_advanced_phone_info(phone_data)
                else:
                    print("Failed to retrieve phone information\n")
            else:
                print("Invalid choice. Please select 1 for IP or 2 for Phone.")
                
        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"An error occurred: {str(e)}\n")


if __name__ == "__main__":
    main()