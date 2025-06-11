import requests
import time
from typing import Optional, Dict
from models import FlightQuery
from config import Config

class FlightAPI:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = Config.BOOKING_API_FLIGHT_URL
        self.headers = {
            'x-rapidapi-host': Config.BOOKING_API_HOST,
            'x-rapidapi-key': api_key
        }
        self.location_cache: Dict[str, str] = {}
    
    def search_location(self, iata_code: str, language_code: Optional[str] = None) -> Optional[str]:
        """Wyszukiwanie lokalizacji z obsługą kodu języka"""
        cache_key = f"{iata_code}_{language_code or 'default'}"
        if cache_key in self.location_cache:
            return self.location_cache[cache_key]
        
        try:
            params = {"query": iata_code}
            if language_code:
                params["languagecode"] = language_code
                
            response = requests.get(
                f"{self.base_url}/searchDestination",
                headers=self.headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    # Preferuj lotniska
                    for location in data['data']:
                        if location.get('type') == 'AIRPORT':
                            location_id = location.get('id', '')
                            self.location_cache[cache_key] = location_id
                            return location_id
                    
                    # Jeśli nie ma lotniska, weź pierwszą dostępną lokalizację
                    location_id = data['data'][0].get('id', '')
                    self.location_cache[cache_key] = location_id
                    return location_id
        except Exception as e:
            print(f"Error searching location {iata_code}: {e}")
        return None
    
    def search_flights(self, query: FlightQuery) -> Optional[dict]:
        """Wyszukiwanie lotów - zwraca surowe dane z API"""
        origin_id = self.search_location(query.origin, query.language_code)
        destination_id = self.search_location(query.destination, query.language_code)
        
        if not origin_id or not destination_id:
            print(f"Could not find location IDs for {query.origin} -> {query.destination}")
            return None
        
        return self._call_api_with_retry(origin_id, destination_id, query)
    
    def _call_api_with_retry(self, origin_id: str, destination_id: str, query: FlightQuery) -> Optional[dict]:
        """Wywołanie API z retry - zwraca surowe dane JSON"""
        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                if attempt > 0:
                    time.sleep(Config.RETRY_DELAY)
                
                # Podstawowe parametry
                params = {
                    "fromId": origin_id,
                    "toId": destination_id,
                    "departDate": query.departure_date,
                    "adults": str(query.adults),
                    "sort": query.sort_option.value,
                    "cabinClass": query.cabin_class.value,
                    "currency_code": query.currency_code,
                    "pageNo": "1"
                }
                
                # Opcjonalne parametry
                if query.return_date:
                    params["returnDate"] = query.return_date
                
                if query.children:
                    params["children"] = query.children
                
                if query.stops:
                    params["stops"] = query.stops.value
                
                print(f"API Request params: {params}")
                
                response = requests.get(
                    f"{self.base_url}/searchFlights", 
                    headers=self.headers, 
                    params=params, 
                    timeout=Config.REQUEST_TIMEOUT
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"DEBUG: API Response status: {data.get('status', 'unknown')}")
                    if data.get('status') != False:
                        print(f"DEBUG: API returned raw data with {len(data.get('data', {}).get('flightOffers', []))} flight offers")
                        return data  # Zwracamy surowe dane JSON
                    else:
                        print(f"DEBUG: API returned status: False, message: {data.get('message', 'no message')}")
                else:
                    print(f"DEBUG: API returned status code: {response.status_code}")
                    print(f"DEBUG: Response: {response.text[:200]}...")
                return None
                
            except Exception as e:
                print(f"API call attempt {attempt + 1} failed: {e}")
                if attempt >= Config.MAX_RETRIES:
                    return None
                continue
        return None