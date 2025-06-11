from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum

class CabinClass(str, Enum):
    ECONOMY = "ECONOMY"
    PREMIUM_ECONOMY = "PREMIUM_ECONOMY"
    BUSINESS = "BUSINESS"
    FIRST = "FIRST"

class SortOption(str, Enum):
    BEST = "BEST"
    CHEAPEST = "CHEAPEST"
    FASTEST = "FASTEST"

class StopOption(str, Enum):
    NONE = "none"  # no preference
    NONSTOP = "0"  # non-stop flights
    ONE_STOP = "1"  # one-stop flights
    TWO_STOP = "2"  # two-stop flights

class TemperatureUnit(str, Enum):
    CELSIUS = "c"
    FAHRENHEIT = "f"

class Units(str, Enum):
    METRIC = "metric"
    IMPERIAL = "imperial"

class FlightQuery(BaseModel):
    origin: str = Field(description="Kod IATA lotniska wylotu") 
    destination: str = Field(description="Kod IATA lotniska docelowego")
    departure_date: str = Field(description="Data wylotu YYYY-MM-DD")
    return_date: Optional[str] = Field(default=None, description="Data powrotu YYYY-MM-DD (opcjonalnie)")
    adults: int = Field(default=1, description="Liczba dorosłych pasażerów (18+)")
    children: Optional[str] = Field(default=None, description="Wiek dzieci oddzielone przecinkami np. '8,15,17'")
    budget: Optional[float] = Field(default=None, description="Budżet w PLN")
    preferred_time: Optional[str] = Field(default=None, description="Preferowana godzina HH:MM")
    cabin_class: CabinClass = Field(default=CabinClass.ECONOMY, description="Klasa kabiny")
    sort_option: SortOption = Field(default=SortOption.CHEAPEST, description="Sortowanie wyników")
    stops: Optional[StopOption] = Field(default=None, description="Preferencje dotyczące przesiadek")
    currency_code: str = Field(default="PLN", description="Kod waluty")
    language_code: Optional[str] = Field(default=None, description="Kod języka dla wyników")

    @property
    def passengers(self) -> int:
        """Całkowita liczba pasażerów dla kompatybilności wstecznej"""
        children_count = 0
        if self.children:
            children_count = len([age for age in self.children.split(',') if age.strip()])
        return self.adults + children_count

class FlightResult(BaseModel):
    airline: str
    departure_time: str
    arrival_time: str
    price: float
    origin_airport: str
    destination_airport: str
    duration: str
    stops: int = Field(default=0, description="Liczba przesiadek")
    is_return: bool = Field(default=False, description="Czy to lot powrotny")
    cabin_class: str = Field(default="ECONOMY", description="Klasa kabiny")



class HotelQuery(BaseModel):
    destination: str = Field(description="Nazwa miasta/miejsca")
    arrival_date: str = Field(description="Data przyjazdu YYYY-MM-DD")
    departure_date: str = Field(description="Data wyjazdu YYYY-MM-DD")
    adults: int = Field(default=1, description="Liczba dorosłych gości (18+)")
    children_age: Optional[str] = Field(default=None, description="Wiek dzieci oddzielone przecinkami")
    room_qty: int = Field(default=1, description="Liczba pokoi")
    price_min: Optional[float] = Field(default=None, description="Minimalna cena za noc")
    price_max: Optional[float] = Field(default=None, description="Maksymalna cena za noc")
    sort_by: Optional[str] = Field(default=None, description="Sortowanie (price, distance, review_score)")
    categories_filter: Optional[str] = Field(default=None, description="Filtr kategorii hoteli")
    units: Units = Field(default=Units.METRIC, description="System miar")
    temperature_unit: TemperatureUnit = Field(default=TemperatureUnit.CELSIUS, description="Jednostka temperatury")
    language_code: str = Field(default="pl", description="Kod języka")
    currency_code: str = Field(default="PLN", description="Kod waluty")
    location: Optional[str] = Field(default=None, description="Lokalizacja użytkownika")
    page_number: int = Field(default=1, description="Numer strony wyników")

    @property
    def total_guests(self) -> int:
        """Całkowita liczba gości"""
        children_count = 0
        if self.children_age:
            children_count = len([age for age in self.children_age.split(',') if age.strip()])
        return self.adults + children_count

    @property
    def nights(self) -> int:
        """Liczba nocy"""
        from datetime import datetime
        try:
            arrival = datetime.strptime(self.arrival_date, "%Y-%m-%d")
            departure = datetime.strptime(self.departure_date, "%Y-%m-%d")
            return (departure - arrival).days
        except:
            return 1

class HotelResult(BaseModel):
    name: str
    price_per_night: float
    total_price: float
    rating: Optional[float] = Field(default=None)
    review_score: Optional[float] = Field(default=None)
    review_count: Optional[int] = Field(default=None)
    distance_from_center: Optional[str] = Field(default=None)
    address: Optional[str] = Field(default=None)
    amenities: List[str] = Field(default=[])
    image_url: Optional[str] = Field(default=None)
    hotel_id: str
    check_in: str
    check_out: str
    room_type: Optional[str] = Field(default=None)
    free_cancellation: bool = Field(default=False)
    breakfast_included: bool = Field(default=False)