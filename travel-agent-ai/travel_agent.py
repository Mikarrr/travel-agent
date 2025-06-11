from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.memory import ConversationBufferMemory
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
        
        # Memory - przechowuje historię rozmowy
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            input_key="query",
            output_key="response"
        )
    
    def process_query(self, user_input: str) -> str:
        """Główna metoda przetwarzająca zapytania użytkownika"""
        try:
            # Pobierz historię rozmowy
            chat_history = self.memory.chat_memory.messages
            history_text = self._format_chat_history(chat_history)

             # DODAJ: Stwórz pełny kontekst z current query
            full_context = history_text
            if history_text and history_text != "Brak poprzednich rozmów.":
                full_context += f"\nUżytkownik (AKTUALNE): {user_input}"
            else:
                full_context = f"Użytkownik: {user_input}"
            
            # KROK 1: LLM rozpoznaje typ i parsuje parametry z kontekstem
            analysis_prompt = ChatPromptTemplate.from_template("""
                Przeanalizuj zapytanie użytkownika i określ czy dotyczy LOTÓW czy HOTELI czy ATRAKCJI.
                Uwzględnij kontekst poprzednich rozmów. 

                HISTORIA ROZMOWY:
                {full_context}

                DZISIEJSZA DATA: {today}

                WSKAZÓWKI ROZPOZNAWANIA:
                - LOTY: "lot", "lecieć", "samolot", "airline", "lotnisko", "lot do", "bilety lotnicze"
                - HOTELE: "hotel", "nocleg", "zakwaterowanie", "rezerwacja hotelu", "gdzie spać", "pobyt"
                - ATRAKCJE: "atrakcje", "co robić", "zwiedzanie", "wycieczki", "co zobaczyć"
                - KONTEKST: Jeśli wcześniej rozmawialiśmy o konkretnym miejscu/dacie, użyj tych informacji

                ZAAWANSOWANE WSKAZÓWKI KONTEKSTOWE:
                - Jeśli zapytanie to "Tak", "Nie", "OK" lub podobna krótka odpowiedź, sprawdź ostatnie pytanie Agenta:
                - Jeśli Agent pytał o loty lub propozycja dotyczyła lotów, uznaj to za LOTY
                - Jeśli Agent pytał o hotele lub propozycja dotyczyła hoteli, uznaj to za HOTELE
                - Jeśli Agent pytał o atrakcje lub propozycja dotyczyła atrakcji, uznaj to za ATRAKCJE

                LOGIKA PRIORYTETÓW:
                1. Jeśli zapytanie to krótka odpowiedź (1-3 słowa), zastosuj ZAAWANSOWANE WSKAZÓWKI KONTEKSTOWE
                2. Jeśli zapytanie zawiera słowa kluczowe LOTY, uznaj to za LOT
                3. Jeśli zapytanie zawiera słowa kluczowe HOTELE, uznaj to za HOTEL
                4. Jeśli zapytanie zawiera słowa kluczowe ATRAKCJE, uznaj to za ATRAKCJE
                5. Jeśli zapytanie nie jest jasne, sprawdź ostatnie pytanie Agenta w historii

                Odpowiedz TYLKO jednym słowem: "LOTY" lub "HOTELE" lub "ATRAKCJE".
                """)
            
            analysis_chain = analysis_prompt | self.llm
            query_type = analysis_chain.invoke({
                "today": datetime.now().strftime('%Y-%m-%d'),
                "full_context": full_context,
            }).content.strip().upper()
            
            print(f"DEBUG: Detected type: {query_type}")
     

            # Przetwórz zapytanie
            if query_type == "HOTELE":
                result = self._handle_hotel_request(user_input, history_text)
            elif query_type == "LOTY":
                result = self._handle_flight_request(user_input, history_text)
            else: 
                result = self._handle_attractions_request(user_input, history_text)
            
            # Zapisz interakcję do memory
            self.memory.save_context(
                {"query": user_input},
                {"response": result}
            )
            print(full_context)
            return result
            
                
        except Exception as e:
            print(f"Error processing query: {e}")
            error_msg = f"❌ Błąd podczas przetwarzania: {str(e)}"
            
            # Zapisz błąd do memory
            self.memory.save_context(
                {"query": user_input},
                {"response": error_msg}
            )
            
            return error_msg
    
    def _handle_flight_request(self, user_input: str, full_context: str) -> str:
        """Obsługa zapytań o loty z kontekstem"""
        try:
            # Parse parametrów lotu z uwzględnieniem historii
            flight_prompt = ChatPromptTemplate.from_template("""
            Wyciągnij parametry lotu z zapytania użytkownika.
            UWZGLĘDNIJ KONTEKST z poprzednich rozmów - jeśli użytkownik wcześniej mówił o konkretnym miejscu lub dacie, użyj tych informacji.
            
            HISTORIA ROZMOWY:
            {full_context}
            
            AKTUALNE ZAPYTANIE: "{query}"
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
            - KONTEKST: Jeśli w historii była mowa o miejscu docelowym, użyj go jako destination
            - KONTEKST: Jeśli w historii była mowa o datach, użyj ich jako odniesienie
            
            {format_instructions}
            """)
            
            flight_chain = flight_prompt | self.llm | self.flight_parser
            query = flight_chain.invoke({
                "query": user_input,
                "today": datetime.now().strftime('%Y-%m-%d'),
                "full_context":   full_context,
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
            return self._format_results("LOTY", user_input, query, simplified_flights, full_context)
            
        except Exception as e:
            print(f"Flight error: {e}")
            return f"❌ Błąd wyszukiwania lotów: {str(e)}"
    
    def _handle_hotel_request(self, user_input: str,  full_context: str) -> str:
        """Obsługa zapytań o hotele z kontekstem"""
        try:
            # Parse parametrów hotelu z uwzględnieniem historii
            hotel_prompt = ChatPromptTemplate.from_template("""
            Wyciągnij parametry hotelu z zapytania użytkownika.
            UWZGLĘDNIJ KONTEKST z poprzednich rozmów - jeśli użytkownik wcześniej mówił o konkretnym miejscu lub datach, użyj tych informacji.
            
            HISTORIA ROZMOWY:
            {full_context}
            
            AKTUALNE ZAPYTANIE: "{query}"
            DZISIEJSZA DATA: {today}
            
            REGUŁY:
            - "jutro" → arrival_date = następny dzień
            - "weekend" → sobota-niedziela
            - "na X dni" → departure_date = arrival_date + X dni
            - "para" → adults=2
            - "tanio" → price_max=200
            - Domyślnie: 2 noce jeśli nie podano departure_date
            - KONTEKST: Jeśli w historii była mowa o miejscu, użyj go jako destination
            - KONTEKST: Jeśli w historii była mowa o datach lotów, dopasuj daty hotelu
            
            {format_instructions}
            """)
            
            hotel_chain = hotel_prompt | self.llm | self.hotel_parser
            query = hotel_chain.invoke({
                "query": user_input,
                "today": datetime.now().strftime('%Y-%m-%d'),
                "full_context":   full_context,
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
            return self._format_results("HOTELE", user_input, query, simplified_hotels, full_context)
            
        except Exception as e:
            print(f"Hotel error: {e}")
            return f"❌ Błąd wyszukiwania hoteli: {str(e)}"
    
    def _handle_attractions_request(self, user_input: str,  full_context: str) -> str:
        """Obsługa zapytań o atrakcje - wykorzystuje wewnętrzną wiedzę Claude'a"""
        try:
            # Wyciągnij kontekst podróży z historii
          
            
            attractions_prompt = ChatPromptTemplate.from_template("""
            Jesteś ekspertem od turystyki i lokalnych atrakcji. Odpowiedz na zapytanie użytkownika o atrakcje, 
            wykorzystując swoją rozległą wiedzę o miejscach, kulturze i turystyce.
            
            HISTORIA ROZMOWY (context podróży):
            {full_context}
            
           
            ZAPYTANIE UŻYTKOWNIKA: "{query}"
            
            INSTRUKCJE:
            
            1. **Wykorzystaj kontekst**: Jeśli wiesz gdzie jedzie użytkownik, skup się na tym miejscu
            2. **Bądź konkretny**: Podaj nazwy konkretnych miejsc, adresów, godzin otwarcia
            3. **Uwzględnij praktyczne info**: ceny, transport, czas potrzebny na zwiedzanie
            4. **Dostosuj do dat**: Jeśli wiesz kiedy jedzie, uwzględnij sezonowość, wydarzenia
            5. **Kategoryzuj**: Podziel na kategorie (zabytki, muzea, restauracje, rozrywka)
            6. **Lokalny kontekst**: Dodaj wskazówki lokalnego przewodnika
            
            STRUKTURA ODPOWIEDZI:
            
            🎯 **[NAZWA MIEJSCA] - Przewodnik po Atrakcjach**
            
            **🏛️ MUST-SEE (najważniejsze zabytki)**
            - [3-5 głównych atrakcji z praktycznymi info]
            
            **🍽️ GDZIE JEŚĆ (lokalne specjały)**
            - [2-3 polecane restauracje/miejsca]
            
            **🎨 KULTURA & ROZRYWKA**
            - [muzea, galerie, wydarzenia]
            
            **💡 WSKAZÓWKI PRAKTYCZNE**
            - Transport lokalny
            - Najlepsze godziny zwiedzania
            - Co zabrać / na co uważać
            - Budżet dzienny
            
            **📅 PLAN DNIA** (jeśli możliwe)
            - Sugerowany harmonogram zwiedzania
            
            Pisz po polsku, używaj emoji, bądź entuzjastyczny ale praktyczny. 
            Jeśli nie ma kontekstu miejsca, zapytaj gdzie jedzie użytkownik.
            """)
            
            attractions_chain = attractions_prompt | self.llm
            result = attractions_chain.invoke({
               "query": user_input,
                "today": datetime.now().strftime('%Y-%m-%d'),
                "full_context":   full_context
            })
            
            return result.content
            
        except Exception as e:
            print(f"Attractions error: {e}")
            return f"❌ Błąd przy wyszukiwaniu atrakcji: {str(e)}"
        
    def _format_results(self, search_type: str, original_query: str, query_params, results, full_context: str) -> str:
        """Formatowanie wyników przez LLM z uwzględnieniem kontekstu"""
        format_prompt = ChatPromptTemplate.from_template("""
        Sformatuj wyniki wyszukiwania dla polskiego użytkownika.
        UWZGLĘDNIJ KONTEKST poprzednich rozmów przy formatowaniu odpowiedzi.
        
        HISTORIA ROZMOWY:
        {full_context}
        
        TYP: {search_type}
        AKTUALNE ZAPYTANIE: "{original_query}"
        PARAMETRY WYSZUKIWANIA: {query_params}
        SUROWE DANE Z API: {results}
        
        UWAGA: Otrzymujesz uproszczone dane (tylko najważniejsze pola) żeby zmniejszyć liczbę tokenów.
        Z CAŁEJ LISTY WYBIERZ TYLKO 5 NAJLEPSZYCH OFERT według kryteriów:
        - Dla LOTÓW: priorytet = 1) bez przesiadek (stops=0), 2) najniższa cena
        - Dla HOTELI: priorytet = najniższa cena (price_per_night)
        
        KONTEKST: Jeśli wcześniej w rozmowie były już wyszukiwania, odnieś się do nich (np. "w porównaniu do wcześniejszych opcji", "zgodnie z Twoimi preferencjami").
        
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
        - Jeśli to ma sens w kontekście rozmowy, zaproponuj następne kroki (np. "czy chcesz teraz poszukać hoteli?" po pokazaniu lotów)
        
        Używaj emoji, polskich znaków, bądź zwięzły ale pomocny.
        """)
        
        format_chain = format_prompt | self.llm
        result = format_chain.invoke({
            "search_type": search_type,
            "original_query": original_query,
            "query_params": str(query_params),
            "results": str(results),
            "full_context": full_context
        })
        
        return result.content
    
    def _format_chat_history(self, messages) -> str:
        """Formatuje historię rozmowy do czytelnej formy"""
        if not messages:
            return "Brak poprzednich rozmów."
        
        history_parts = []
        for i in range(0, len(messages), 2):
            if i + 1 < len(messages):
                user_msg = messages[i].content
                ai_msg = messages[i + 1].content
                
                
                
                history_parts.append(f"Użytkownik: {user_msg}")
                history_parts.append(f"Agent: {ai_msg}")
        
      
        
        return "\n".join(history_parts)
    
    def get_chat_history(self) -> str:
        """Publiczna metoda do pobierania historii rozmowy"""
        return self._format_chat_history(self.memory.chat_memory.messages)
    
    def clear_memory(self):
        """Czyści historię rozmowy"""
        self.memory.clear()
        print("Historia rozmowy została wyczyszczona.")
    
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