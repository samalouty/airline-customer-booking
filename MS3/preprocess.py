import json
import os
from openai import OpenAI

# Initialize Client (Example uses Groq for fast/free inference, but works with OpenAI/Ollama)
# Replace 'api_key' and 'base_url' with your specific provider details.
client = OpenAI(
    api_key=os.environ.get("GROQ_API_KEY", "your-api-key-here"),
    base_url="https://api.groq.com/openai/v1" 
)

SYSTEM_PROMPT = """
You are an expert Intent Classifier and Entity Extractor for an Airline Graph Database.
Your task is to analyze the User Query and map it to EXACTLY ONE of the following intents.
You must also extract the required entities strictly.

INTENT LIST:
1. "analyze_fleet_delays" (analyzes delays by aircraft type). Entities: None.
2. "analyze_airport_delays" (analyzes delays for an origin airport). Entities: "origin_code" (e.g., ORD, LAX).
3. "analyze_generational_satisfaction" (analyzes food score by generation). Entities: "generation" (e.g., Millennial, Gen X).
4. "analyze_loyalty_rating" (analyzes food score by loyalty/class). Entities: "loyalty_tier", "cabin_class".
5. "find_long_haul_flights" (filters flights by distance). Entities: "origin_code", "dest_code", "min_miles" (integer).
6. "analyze_route_frequency" (counts flights from origin). Entities: "origin_code".
7. "find_severe_service_issues" (finds high delay + low score). Entities: "min_delay" (int), "max_score" (int).
8. "analyze_demographic_on_fleet" (correlates generation with aircraft). Entities: "generation", "aircraft_type".
9. "lookup_passenger_record" (finds specific passenger). Entities: "record_locator".
10. "lookup_feedback_details" (finds specific feedback). Entities: "feedback_id".

OUTPUT FORMAT:
Return ONLY a valid JSON object. Do not add markdown or conversational text.
Example:
{
    "intent": "analyze_airport_delays",
    "entities": {
        "origin_code": "JFK"
    }
}
"""

def get_intent_and_entities(user_query):
    """
    Sends user query to LLM and parses JSON response for Intent and NER.
    """
    try:
        response = client.chat.completions.create(
            model="llama3-8b-8192", # Use a lightweight model
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0 # Strict determinism needed for code
        )
        
        # Extract content
        raw_content = response.choices[0].message.content.strip()
        
        # Helper to clean markdown if the LLM is stubborn (e.g., ```json ... ```)
        if raw_content.startswith("```json"):
            raw_content = raw_content.split("```json")[1].split("```")[0].strip()
        elif raw_content.startswith("```"):
            raw_content = raw_content.split("```")[1].split("```")[0].strip()

        parsed_data = json.loads(raw_content)
        return parsed_data

    except json.JSONDecodeError:
        print(f"Error: LLM did not return valid JSON. Raw: {raw_content}")
        return None
    except Exception as e:
        print(f"API Error: {e}")
        return None

# --- Testing Block ---
if __name__ == "__main__":
    # Test 1: Operational
    q1 = "Show me delay statistics for flights out of ORD."
    print(f"Query: {q1}\nResult: {get_intent_and_entities(q1)}\n")

    # Test 2: Semantic/Complex
    q2 = "Find flights with severe delays over 60 mins and food ratings below 2."
    print(f"Query: {q2}\nResult: {get_intent_and_entities(q2)}\n")