#!/usr/bin/env python3
import os
import sys
import json

# Add the project root to the python path so we can import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.openai_client import get_answer
from config.neo4j_client import driver
from MS3.base_retrieve import Neo4jRetriever

class QueryPreprocessor:
    """
    Handles preprocessing of user queries, including intent classification and entity extraction.
    """
    
    # Schema context from Create_kg.py (simplified for the prompt)
    SCHEMA_CONTEXT = """
    Nodes and Properties:
    - Passenger: record_locator, loyalty_program_level, generation
    - Journey: feedback_ID, food_satisfaction_score, arrival_delay_minutes, actual_flown_miles, number_of_legs, passenger_class
    - Flight: flight_number, fleet_type_description
    - Airport: station_code (origin_code, dest_code)
    
    Relationships:
    - (Passenger)-[:TOOK]->(Journey)
    - (Journey)-[:ON]->(Flight)
    - (Flight)-[:DEPARTS_FROM]->(Airport)
    - (Flight)-[:ARRIVES_AT]->(Airport)
    """

    def __init__(self, retriever):
        """
        Initialize the preprocessor with a retriever instance to access available intents.
        """
        self.retriever = retriever

    def classify_intent(self, user_input):
        """
        Uses LLM to classify the user's input into one of the available intents.
        """
        available_intents = self.retriever.get_available_intents()
        
        prompt = f"""
        You are an intent classifier for an airline customer booking system.
        
        User Input: "{user_input}"
        
        Available Intents:
        {json.dumps(available_intents, indent=2)}
        
        Task:
        Analyze the user input and map it to exactly one of the available intents.
        Return ONLY the intent key. If the input does not match any intent, return "unknown".
        """
        
        intent = get_answer(prompt).strip()
        
        # Basic cleanup in case the LLM adds quotes or extra whitespace
        intent = intent.replace('"', '').replace("'", "").strip()
        
        if intent not in available_intents:
            return "unknown"
            
        return intent

    def extract_entities(self, user_input, intent):
        """
        Uses LLM to extract entities based on the user input and the identified intent.
        """
        
        prompt = f"""
        You are an entity extractor for an airline database query system.
        
        Schema Context:
        {self.SCHEMA_CONTEXT}
        
        User Input: "{user_input}"
        Identified Intent: "{intent}"
        
        Task:
        Extract the necessary parameters (entities) from the user input to execute the Cypher query for the given intent.
        Return the result as a valid JSON object where keys are the parameter names expected by the Cypher query.
        
        Standard Parameter Names (use these keys if applicable):
        - min_delay, max_delay (for arrival_delay_minutes)
        - min_score, max_score (for food_satisfaction_score)
        - min_miles, max_miles (for actual_flown_miles)
        - loyalty_level, loyalty_levels (for loyalty_program_level)
        - generation, generations
        - passenger_class
        - fleet_type (for fleet_type_description)
        - station_code, origin, dest
        - vip_id (for record_locator)
        
        If a parameter is missing or cannot be inferred, do not include it in the JSON.
        
        Example Output:
        {{
            "min_delay": 60,
            "max_score": 2,
            "loyalty_level": "Platinum"
        }}
        """
        
        response = get_answer(prompt)
        
        try:
            # Attempt to parse the JSON response
            # Sometimes LLMs wrap JSON in markdown code blocks
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]
                
            entities = json.loads(response.strip())
            return entities
        except json.JSONDecodeError:
            print(f"Error parsing entities JSON: {response}")
            return {}

    def get_embedding(self, text):
        """
        Placeholder for future embedding implementation.
        """
        # TODO: Implement embedding generation logic here
        pass

def main():
    print("--- Airline Customer Booking System Preprocessing ---")
    print("Please enter your query (or type 'exit' to quit):")
    
    # Initialize components
    # We pass the driver explicitly, though Neo4jRetriever can handle it being None (using default)
    retriever = Neo4jRetriever(driver)
    processor = QueryPreprocessor(retriever)
    
    while True:
        user_input = input("\n> ")
        if user_input.lower() in ['exit', 'quit']:
            break
            
        print("Classifying intent...")
        intent = processor.classify_intent(user_input)
        print(f"Identified Intent: {intent}")
        
        if intent == "unknown":
            print("Could not understand the intent. Please try again.")
            continue
            
        print("Extracting entities...")
        entities = processor.extract_entities(user_input, intent)
        print(f"Extracted Entities: {entities}")
        
        # Placeholder for embedding
        processor.get_embedding(user_input)
        
        print("Executing query...")
        results = retriever.run_query(intent, entities)
        
        print("\n--- Query Results ---")
        if isinstance(results, list):
            if not results:
                print("No results found.")
            else:
                for res in results:
                    print(res)
        else:
            print(results)

if __name__ == "__main__":
    main()
