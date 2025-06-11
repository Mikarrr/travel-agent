from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from datetime import datetime, timedelta

from models import FlightQuery, HotelQuery
from config import Config
from flight_api import FlightAPI
from hotel_api import HotelAPI

class TravelAgent:
    def __init__(self, claude_api_key: str, booking_api_key: str):
        self.llm = ChatAnthropic(
            api_key=claude_api_key,
            model=Config.CLAUDE_MODEL,
            temperature=Config.CLAUDE_TEMPERATURE
        )
        
        # API clients
        self.flight_api = FlightAPI(booking_api_key)
        self.hotel_api = HotelAPI(booking_api_key)
        
        # Parsery
        self.flight_parser = PydanticOutputParser(pydantic_object=FlightQuery)
        self.hotel_parser = PydanticOutputParser(pydantic_object=HotelQuery)
    
    def process_query(self, user_input: str) -> str:
        """Główna metoda przetwarzająca zapytania użytkownika"""
        try:
            # KROK 1: LLM rozpoznaje typ i parsuje parametry
            analysis_prompt = ChatPromptTemplate.from_template("""
            Przeanalizuj zapytanie użytkownika i określ czy dotyczy LOTÓW czy HOTELI.
            
            ZAPYTANIE: "{query}"
            DZISIEJSZA DATA: {today}
            
            WSKAZÓWKI ROZPOZNAWANIA:
            - LOTY: "lot", "lecieć", "samolot", "airline", "lotnisko", "lot do", "bilety lotnicze"
            - HOTELE: "hotel", "nocleg", "zakwaterowanie", "rezerwacja hotelu", "gdzie spać", "pobyt"
            
            Odpowiedz TYLKO jednym słowem: "FLIGHT" lub "HOTEL"
            """)
            
            analysis_chain = analysis_prompt | self.llm
            query_type = analysis_chain.invoke({
                "query": user_input,
                "today": datetime.now().strftime('%Y-%m-%d')
            }).content.strip().upper()
            
            print(f"DEBUG: Detected type: {query_type}")
            
            if query_type == "HOTEL":
                return self._handle_hotel_request(user_input)
            else:  # Default to FLIGHT
                return self._handle_flight_request(user_input)
                
        except Exception as e:
            print(f"Error processing query: {e}")
            return f"❌ Błąd podczas przetwarzania: {str(e)}"
    
    def _handle_flight_request(self, user_input: str) -> str:
        """Obsługa zapytań o loty"""
        try:
            # Parse parametrów lotu
            flight_prompt = ChatPromptTemplate.from_template("""
            Wyciągnij parametry lotu z zapytania użytkownika.
            
            ZAPYTANIE: "{query}"
            DZISIEJSZA DATA: {today}
            
            KODY IATA: WAW=Warszawa, CDG=Paryż, LHR=Londyn, BER=Berlin, FCO=Rzym, MAD=Madryt, BCN=Barcelona, AMS=Amsterdam, VIE=Wiedeń, PRG=Praga, BUD=Budapeszt, KRK=Kraków, GDN=Gdańsk, WRO=Wrocław
            
            REGUŁY:
            - Origin domyślnie: "WAW" 
            - "jutro" → następny dzień
            - "para" → adults=2
            - "dzieci X lat" → children="X"
            - "tanio" → budget=800, sort=CHEAPEST
            - "bezpośredni" → stops="0"
            - Klasa domyślnie: ECONOMY
            
            {format_instructions}
            """)
            
            flight_chain = flight_prompt | self.llm | self.flight_parser
            query = flight_chain.invoke({
                "query": user_input,
                "today": datetime.now().strftime('%Y-%m-%d'),
                "format_instructions": self.flight_parser.get_format_instructions()
            })
            
            # Fix dat jeśli potrzeba
            if not query.departure_date or query.departure_date == "jutro":
                query.departure_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            if not query.destination:
                return "❌ Nie rozpoznałem celu podróży. Przykład: 'lot do Paryża jutro'"
            
            print(f"DEBUG: Flight {query.origin} → {query.destination} na {query.departure_date}")
            
            # Szukaj lotów
            api_data = self.flight_api.search_flights(query)
            
            if not api_data or not api_data.get('data', {}).get('flightOffers'):
                return f"❌ Brak lotów {query.origin} → {query.destination} na {query.departure_date}"
            
            # Wyciągnij tylko potrzebne dane żeby zmniejszyć tokeny
            simplified_flights = self._extract_flight_essentials(api_data.get('data', {}).get('flightOffers', []))
            
            print(f"DEBUG: Simplified {len(simplified_flights)} flight offers")
            
            # Formatuj wyniki - przekaż tylko essentials
            return self._format_results("LOTY", user_input, query, simplified_flights)
            
        except Exception as e:
            print(f"Flight error: {e}")
            return f"❌ Błąd wyszukiwania lotów: {str(e)}"
    
    def _handle_hotel_request(self, user_input: str) -> str:
        """Obsługa zapytań o hotele"""
        try:
            # Parse parametrów hotelu
            hotel_prompt = ChatPromptTemplate.from_template("""
            Wyciągnij parametry hotelu z zapytania użytkownika.
            
            ZAPYTANIE: "{query}"
            DZISIEJSZA DATA: {today}
            
            REGUŁY:
            - "jutro" → arrival_date = następny dzień
            - "weekend" → sobota-niedziela
            - "na X dni" → departure_date = arrival_date + X dni
            - "para" → adults=2
            - "tanio" → price_max=200
            - Domyślnie: 2 noce jeśli nie podano departure_date
            
            {format_instructions}
            """)
            
            hotel_chain = hotel_prompt | self.llm | self.hotel_parser
            query = hotel_chain.invoke({
                "query": user_input,
                "today": datetime.now().strftime('%Y-%m-%d'),
                "format_instructions": self.hotel_parser.get_format_instructions()
            })
            
            # Fix dat
            if not query.arrival_date or query.arrival_date == "jutro":
                query.arrival_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            if not query.departure_date:
                arrival = datetime.strptime(query.arrival_date, '%Y-%m-%d')
                query.departure_date = (arrival + timedelta(days=2)).strftime('%Y-%m-%d')
            
            if not query.destination:
                return "❌ Nie rozpoznałem miejsca pobytu. Przykład: 'hotel w Paryżu na weekend'"
            
            print(f"DEBUG: Hotel {query.destination} {query.arrival_date} → {query.departure_date}")
            
            # Szukaj hoteli
            api_data = self.hotel_api.search_hotels(query)
            
            if not api_data or not api_data.get('data', {}).get('hotels'):
                return f"❌ Brak hoteli w {query.destination} na {query.arrival_date}"
            
            # Wyciągnij tylko potrzebne dane żeby zmniejszyć tokeny
            simplified_hotels = self._extract_hotel_essentials(api_data.get('data', {}).get('hotels', []))
            
            print(f"DEBUG: Simplified {len(simplified_hotels)} hotel offers")
            
            # Formatuj wyniki - przekaż tylko essentials
            return self._format_results("HOTELE", user_input, query, simplified_hotels)
            
        except Exception as e:
            print(f"Hotel error: {e}")
            return f"❌ Błąd wyszukiwania hoteli: {str(e)}"
    
    def _format_results(self, search_type: str, original_query: str, query_params, results) -> str:
        """Formatowanie wyników przez LLM"""
        format_prompt = ChatPromptTemplate.from_template("""
        Sformatuj wyniki wyszukiwania dla polskiego użytkownika.
        
        TYP: {search_type}
        ZAPYTANIE: "{original_query}"
        PARAMETRY WYSZUKIWANIA: {query_params}
        SUROWE DANE Z API: {results}
        
        UWAGA: Otrzymujesz uproszczone dane (tylko najważniejsze pola) żeby zmniejszyć liczbę tokenów.
        Z CAŁEJ LISTY WYBIERZ TYLKO 5 NAJLEPSZYCH OFERT według kryteriów:
        - Dla LOTÓW: priorytet = 1) bez przesiadek (stops=0), 2) najniższa cena
        - Dla HOTELI: priorytet = najniższa cena (price_per_night)
        
        FORMATOWANIE:
        
        Dla LOTÓW ✈️:
        - Masz listę lotów z polami: price, airline, departure_time, arrival_time, origin_airport, destination_airport, stops, duration
        - WYBIERZ 5 NAJLEPSZYCH (priorytet: stops=0, potem najniższa price)
        - Nagłówek z trasą i datą
        - Lista 5 wybranych lotów z: linia, czas, cena PLN, przesiadki, lotniska
        - Badge klasy: 💺(economy - domyślnie)
        - Jeśli >1 pasażer, podaj cenę za osobę
        
        Dla HOTELI 🏨:
        - Masz listę hoteli z polami: name, price_per_night, rating, accessibility_label (zawiera lokalizację i oceny tekstowe)
        - WYBIERZ 5 NAJTAŃSZYCH (najniższa price_per_night)
        - Nagłówek z miastem i datami  
        - Lista 5 wybranych hoteli z: nazwa, ocena ⭐ (rating), cena/noc PLN, lokalizacja z accessibility_label
        - Dodatki: sprawdź accessibility_label pod kątem informacji o udogodnieniach
        
        Na końcu:
        - Krótkie podsumowanie budżetu
        - 2-3 praktyczne wskazówki
        
        Używaj emoji, polskich znaków, bądź zwięzły ale pomocny.
        """)
        
        format_chain = format_prompt | self.llm
        result = format_chain.invoke({
            "search_type": search_type,
            "original_query": original_query,
            "query_params": str(query_params),
            "results": str(results)
        })
        
        return result.content
    
    def _extract_flight_essentials(self, flights: list) -> list:
        """Wyciąga tylko najważniejsze dane z lotów żeby zmniejszyć tokeny"""
        essentials = []
        
        for flight in flights[:20]:  # Ogranicz do 20 lotów max
            try:
                # Cena
                price_breakdown = flight.get('priceBreakdown', {})
                total = price_breakdown.get('total', {})
                units = total.get('units', 0)
                nanos = total.get('nanos', 0)
                price = float(units) + (float(nanos) / 1000000000)
                
                # Pierwszy segment (główny lot)
                segments = flight.get('segments', [])
                if not segments:
                    continue
                    
                segment = segments[0]
                legs = segment.get('legs', [])
                if not legs:
                    continue
                
                first_leg = legs[0]
                last_leg = legs[-1]
                
                # Podstawowe dane
                essential = {
                    'price': price,
                    'airline': first_leg.get('carriersData', [{}])[0].get('name', 'Unknown'),
                    'departure_time': first_leg.get('departureTime', ''),
                    'arrival_time': last_leg.get('arrivalTime', ''),
                    'origin_airport': first_leg.get('departureAirport', {}).get('code', ''),
                    'destination_airport': last_leg.get('arrivalAirport', {}).get('code', ''),
                    'stops': max(0, len(legs) - 1),
                    'duration': segment.get('totalTime', 0)
                }
                
                essentials.append(essential)
                
            except Exception as e:
                print(f"Error extracting flight essentials: {e}")
                continue
        
        return essentials
    
    def _extract_hotel_essentials(self, hotels: list) -> list:
        """Wyciąga tylko najważniejsze dane z hoteli żeby zmniejszyć tokeny"""
        essentials = []
        
        for hotel in hotels[:20]:  # Ogranicz do 20 hoteli max
            try:
                # Nazwa
                name = "Unknown Hotel"
                if 'property' in hotel and isinstance(hotel['property'], dict):
                    name = hotel['property'].get('name', 'Unknown Hotel')
                elif 'name' in hotel:
                    name = hotel.get('name', 'Unknown Hotel')
                
                # Cena
                price = 0
                if 'property' in hotel and isinstance(hotel['property'], dict):
                    price_info = hotel['property'].get('priceBreakdown', {})
                    if price_info and isinstance(price_info, dict):
                        gross_price = price_info.get('grossPrice', {})
                        if isinstance(gross_price, dict):
                            price = gross_price.get('value', 0)
                
                # Ocena z accessibilityLabel
                rating = 0
                accessibility_label = hotel.get('accessibilityLabel', '')
                if accessibility_label:
                    import re
                    rating_match = re.search(r'(\d+,\d+|\d+\.\d+)', accessibility_label)
                    if rating_match:
                        try:
                            rating = float(rating_match.group(1).replace(',', '.'))
                        except:
                            pass
                
                essential = {
                    'name': name,
                    'price_per_night': price,
                    'rating': rating,
                    'accessibility_label': accessibility_label[:100] if accessibility_label else ''  # Skróć label
                }
                
                essentials.append(essential)
                
            except Exception as e:
                print(f"Error extracting hotel essentials: {e}")
                continue
        
        return essentials


class TravelAgentFactory:
    @staticmethod
    def create() -> TravelAgent:
        if not Config.validate():
            raise ValueError("Brak kluczy API w .env")
        
        return TravelAgent(
            claude_api_key=Config.CLAUDE_API_KEY,
            booking_api_key=Config.RAPIDAPI_KEY
        )