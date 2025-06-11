import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Keys
    CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
    RAPIDAPI_KEY = os.getenv('RAPIDAPI_KEY')
    
    # Booking API Configuration
    BOOKING_API_HOST = 'booking-com15.p.rapidapi.com'
    BOOKING_API_FLIGHT_URL = f'https://{BOOKING_API_HOST}/api/v1/flights'
    BOOKING_API_HOTEL_URL = f'https://{BOOKING_API_HOST}/api/v1/hotels'
    
    # Claude Configuration
    CLAUDE_MODEL = 'claude-sonnet-4-20250514'
    CLAUDE_TEMPERATURE = 0.3
    
    # API Limits and Timeouts
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds
    REQUEST_TIMEOUT = 30  # seconds
    MAX_RESULTS = 10
    
    # Default Values
    DEFAULT_CURRENCY = 'PLN'
    DEFAULT_CABIN_CLASS = 'ECONOMY'
    DEFAULT_SORT = 'CHEAPEST'
    DEFAULT_LANGUAGE = 'pl'
    
    @classmethod
    def validate(cls) -> bool:
        """Sprawdź czy wszystkie wymagane klucze API są dostępne"""
        required_keys = [cls.CLAUDE_API_KEY, cls.RAPIDAPI_KEY]
        return all(key is not None and key.strip() != '' for key in required_keys)
    
    @classmethod
    def get_missing_keys(cls) -> list:
        """Zwróć listę brakujących kluczy API"""
        missing = []
        if not cls.CLAUDE_API_KEY:
            missing.append('CLAUDE_API_KEY')
        if not cls.RAPIDAPI_KEY:
            missing.append('RAPIDAPI_KEY')
        return missing