from travel_agent import TravelAgentFactory

def main():
    try:
        agent = TravelAgentFactory.create()
        print("🌍 TRAVEL AGENT")
        print("💡 Przykłady: 'lot do Paryża jutro rano', 'Barcelona dla 2 osób budżet 800zł'")
        
        while True:
            user_input = input("\n💬 Ty: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 Pa!")
                break
            
            if user_input:
                print(f"\n🤖 Agent:\n{agent.process_query(user_input)}")
                
    except Exception as e:
        print(f"❌ Błąd: {e}")

if __name__ == "__main__":
    main()