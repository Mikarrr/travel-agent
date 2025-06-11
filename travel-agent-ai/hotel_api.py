import requests
import time
from typing import Optional, Dict, Tuple
from models import HotelQuery
from config import Config

class HotelAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = Config.BOOKING_API_HOTEL_URL
        self.headers = {
            'x-rapidapi-host': Config.BOOKING_API_HOST,
            'x-rapidapi-key': api_key
        }
        self.destination_cache: Dict[str, Tuple[str, str]] = {}
    
    def search_destination(self, query: str) -> Optional[Tuple[str, str]]:
        """Wyszukiwanie destynacji hotelowej - zwraca (dest_id, search_type)"""
        if query in self.destination_cache:
            return self.destination_cache[query]
        
        try:
            response = requests.get(
                f"{self.base_url}/searchDestination",
                headers=self.headers,
                params={"query": query},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    # Preferuj miasta i regiony nad hotelami
                    for destination in data['data']:
                        dest_type = destination.get('dest_type', '').upper()
                        if dest_type in ['CITY', 'REGION', 'DISTRICT']:
                            dest_id = destination.get('dest_id')
                            search_type = dest_type
                            if dest_id:
                                result = (str(dest_id), search_type)
                                self.destination_cache[query] = result
                                return result
                    
                    # Jeśli nie ma miasta, weź pierwszą dostępną destynację
                    first_dest = data['data'][0]
                    dest_id = first_dest.get('dest_id')
                    search_type = first_dest.get('dest_type', 'CITY').upper()
                    if dest_id:
                        result = (str(dest_id), search_type)
                        self.destination_cache[query] = result
                        return result
        except Exception as e:
            print(f"Error searching hotel destination {query}: {e}")
        return None
    
    def search_hotels(self, query: HotelQuery) -> Optional[dict]:
        """Wyszukiwanie hoteli - zwraca surowe dane z API"""
        destination_info = self.search_destination(query.destination)
        
        if not destination_info:
            print(f"Could not find destination for: {query.destination}")
            return None
        
        dest_id, search_type = destination_info
        return self._call_api_with_retry(dest_id, search_type, query)
    
    def _call_api_with_retry(self, dest_id: str, search_type: str, query: HotelQuery) -> Optional[dict]:
        """Wywołanie API z retry - zwraca surowe dane JSON"""
        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                if attempt > 0:
                    time.sleep(Config.RETRY_DELAY)
                
                # Podstawowe wymagane parametry
                params = {
                    "dest_id": dest_id,
                    "search_type": search_type,
                    "arrival_date": query.arrival_date,
                    "departure_date": query.departure_date,
                    "adults": str(query.adults),
                    "room_qty": str(query.room_qty),
                    "page_number": str(query.page_number),
                    "units": query.units.value,
                    "temperature_unit": query.temperature_unit.value,
                    "languagecode": query.language_code,
                    "currency_code": query.currency_code
                }
                
                # Opcjonalne parametry
                if query.children_age:
                    params["children_age"] = query.children_age
                
                if query.price_min:
                    params["price_min"] = str(query.price_min)
                
                if query.price_max:
                    params["price_max"] = str(query.price_max)
                
                if query.sort_by:
                    params["sort_by"] = query.sort_by
                
                if query.categories_filter:
                    params["categories_filter"] = query.categories_filter
                
                if query.location:
                    params["location"] = query.location
                
                print(f"Hotel API Request params: {params}")
                
                response = requests.get(
                    f"{self.base_url}/searchHotels",
                    headers=self.headers,
                    params=params,
                    timeout=Config.REQUEST_TIMEOUT
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"DEBUG: Hotel API Response status: {data.get('status', 'unknown')}")
                    if data.get('status') != False:
                        hotel_offers = data.get('data', {}).get('hotels', [])
                        print(f"DEBUG: API returned raw data with {len(hotel_offers)} hotel offers")
                        return data  # Zwracamy surowe dane JSON
                    else:
                        print(f"DEBUG: Hotel API returned status: False, message: {data.get('message', 'no message')}")
                else:
                    print(f"DEBUG: Hotel API returned status code: {response.status_code}")
                    print(f"DEBUG: Response: {response.text[:200]}...")
                return None
                
            except Exception as e:
                print(f"Hotel API call attempt {attempt + 1} failed: {e}")
                if attempt >= Config.MAX_RETRIES:
                    return None
                continue
        return None