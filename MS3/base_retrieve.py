#!/usr/bin/env python3
from neo4j import GraphDatabase
import os
import sys

# --- Configuration ---
# Ensure this matches your actual project structure
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.neo4j_client import driver as default_driver

class Neo4jRetriever:
    def __init__(self, driver=None):
        self.driver = driver if driver else default_driver

    def get_available_intents(self):
        return [
            "analyze_delays",
            "analyze_satisfaction",
            "search_network",
            "analyze_issues",
            "lookup_details"
        ]

    # ==========================================
    # HELPER: Data Cleaning & Normalization
    # ==========================================
    def normalize_entities(self, entities):
        """
        Cleans LLM outputs to match Database constraints.
        1. Maps 'Boomers' -> 'Boomer' (De-pluralization)
        2. Maps synonyms (vip_id -> record_locator)
        """
        clean = entities.copy()

        # --- Fix 1: Handle Plurals for Generations ---
        if 'generation' in clean:
            gen = clean['generation'].lower()
            if 'boomer' in gen: clean['generation'] = 'Boomer'
            elif 'millennial' in gen: clean['generation'] = 'Millennial'
            elif 'gen x' in gen: clean['generation'] = 'Gen X'
            elif 'gen z' in gen: clean['generation'] = 'Gen Z'
        
        # --- Fix 2: Key Mapping ---
        # Map whatever the LLM gave to standard variable names for Cypher
        if 'origin_code' in clean: clean['origin'] = clean.pop('origin_code')
        if 'dest_code' in clean: clean['dest'] = clean.pop('dest_code')
        if 'vip_id' in clean: clean['record_locator'] = clean.pop('vip_id')
        if 'loyalty_level' in clean: clean['loyalty_tier'] = clean.pop('loyalty_level')
        if 'passenger_class' in clean: clean['class'] = clean.pop('passenger_class')

        return clean

    # ==========================================
    # LOGIC: The Internal Router
    # ==========================================
    def get_query_for_intent(self, intent, entities):
        """
        Maps Intent + Entities -> Specific Cypher Query
        """
        
        # 1. INTENT: search_network
        if intent == "search_network":
            if 'origin' in entities and 'dest' in entities and 'min_miles' in entities:
                return """
                    MATCH (origin:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(dest:Airport {station_code: $dest})
                    MATCH (j:Journey)-[:ON]->(f)
                    WHERE j.actual_flown_miles > $min_miles
                    RETURN DISTINCT f.flight_number, f.fleet_type_description, j.actual_flown_miles
                """
            if 'origin' in entities and 'dest' in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    RETURN f.flight_number, f.fleet_type_description
                """
            if 'origin' in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport)
                    RETURN o.station_code AS origin, d.station_code AS destination, count(f) AS flight_options_count
                    ORDER BY flight_options_count DESC LIMIT 10
                """

        # 2. INTENT: analyze_satisfaction
        if intent == "analyze_satisfaction":
            if 'loyalty_tier' in entities and 'class' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.loyalty_program_level = $loyalty_tier AND j.passenger_class = $class
                    RETURN avg(j.food_satisfaction_score) AS average_rating, count(j) AS total_trips
                """
            if 'generation' in entities and 'fleet_type' in entities:
                # FIX: Changed '=' to 'CONTAINS' for fleet_type_description
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE p.generation = $generation 
                      AND f.fleet_type_description CONTAINS $fleet_type
                    RETURN p.generation, f.fleet_type_description, avg(j.food_satisfaction_score) AS average_food_rating
                """
            if 'generation' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.generation = $generation
                    RETURN p.generation AS generation, avg(j.food_satisfaction_score) AS average_food_rating
                """
            return "MATCH (j:Journey) RETURN avg(j.food_satisfaction_score) as global_avg"

        # 3. INTENT: analyze_delays
        if intent == "analyze_delays":
            if 'origin' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport {station_code: $origin})
                    RETURN a.station_code AS airport, min(j.arrival_delay_minutes) AS min_delay, max(j.arrival_delay_minutes) AS max_delay, avg(j.arrival_delay_minutes) AS avg_delay
                """
            return """
                MATCH (j:Journey)-[:ON]->(f:Flight)
                RETURN f.fleet_type_description AS aircraft_type, avg(j.arrival_delay_minutes) AS average_delay
                ORDER BY average_delay DESC LIMIT 5
            """

        # 4. INTENT: analyze_issues
        if intent == "analyze_issues":
            if 'min_delay' in entities and 'max_score' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.arrival_delay_minutes > $min_delay AND j.food_satisfaction_score <= $max_score
                    RETURN f.flight_number, j.arrival_delay_minutes, j.food_satisfaction_score, j.feedback_ID
                    LIMIT 20
                """

        # 5. INTENT: lookup_details
        if intent == "lookup_details":
            if 'record_locator' in entities:
                # CHANGED: We now return a single map called 'full_record' 
                # instead of 3 separate nodes (p, j, f).
                return """
                    MATCH (p:Passenger {record_locator: $record_locator})-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    RETURN {
                        passenger: properties(p),
                        journey: properties(j),
                        flight: properties(f)
                    } AS full_record
                """
            
            if 'feedback_id' in entities:
                # OPTIONAL: You can treat this one the same way for consistency
                return """
                    MATCH (j:Journey {feedback_ID: $feedback_id})
                    OPTIONAL MATCH (p:Passenger)-[:TOOK]->(j)-[:ON]->(f:Flight)
                    RETURN {
                        journey: properties(j),
                        passenger: properties(p),
                        flight_number: f.flight_number
                    } AS feedback_details
                """

        return None

    def run_query(self, intent, entities):
        # 1. Normalize Entities (Fixes 'Boomers' -> 'Boomer')
        clean_params = self.normalize_entities(entities)
        clean_params = {k: v for k, v in clean_params.items() if v is not None}
        
        # 2. Get Query
        cypher_query = self.get_query_for_intent(intent, clean_params)
        
        if not cypher_query:
            return f"Error: Could not construct query for intent '{intent}' with entities {list(clean_params.keys())}"

        try:
            if self.driver is None:
                return "Database Error: Driver not initialized."
            
            # Debug Print
            print(f"--- Executing Query for '{intent}' ---")
            print(f"Params: {clean_params}")
            print(f"Cypher Query:\n{cypher_query}")
            print(f"--- End Query ---\n")
            
            records, summary, keys = self.driver.execute_query(
                cypher_query,
                clean_params,
                database_="neo4j", 
            )
            
            # --- Fix 2: Result Serialization ---
            # Converts Neo4j Node objects (<Node...>) into clean Python Dictionaries
            serialized_results = []
            for record in records:
                row = {}
                for key, value in record.items():
                    # Check if value is a Neo4j Node/Relationship (has 'items' method like a dict)
                    # or explicitly check type if needed, but 'hasattr' is duck-typing safe
                    if hasattr(value, 'items') and callable(value.items):
                        row[key] = dict(value.items()) # Convert Node to Dict
                    else:
                        row[key] = value
                serialized_results.append(row)

            return serialized_results

        except Exception as e:
            return f"Database Error: {e}"

# --- Usage Example ---
if __name__ == "__main__":
    retriever = Neo4jRetriever()
    
    print("\n--- TEST 1: Boomers Plural Fix ---")
    # Input 'Boomers' -> Should convert to 'Boomer' and find results
    print(retriever.run_query("analyze_satisfaction", {'generation': 'Boomers'}))

    print("\n--- TEST 2: Record Lookup Clean Output Fix ---")
    # Should output clean JSON, not <Node ...>
    print(retriever.run_query("lookup_details", {'vip_id': 'EPXXW8'}))