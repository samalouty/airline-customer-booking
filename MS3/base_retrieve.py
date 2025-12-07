#!/usr/bin/env python3
from neo4j import GraphDatabase
import os
import sys

# --- Configuration ---
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

    def get_query_for_intent(self, intent, entities):
        """
        Maps a Broad Intent + Available Entities -> Specific Cypher Query.
        Includes parameter normalization to handle LLM variations.
        """
        
        # Helper to check keys safely
        has_origin = 'origin' in entities or 'origin_code' in entities
        has_dest = 'dest' in entities or 'dest_code' in entities or 'destination' in entities
        
        # Normalize keys for Cypher (Map whatever the LLM gave to standard variable names)
        # This ensures if LLM gives 'origin', we can use $origin in Cypher
        if 'origin_code' in entities: entities['origin'] = entities.pop('origin_code')
        if 'dest_code' in entities: entities['dest'] = entities.pop('dest_code')
        if 'vip_id' in entities: entities['record_locator'] = entities.pop('vip_id')
        if 'loyalty_level' in entities: entities['loyalty_tier'] = entities.pop('loyalty_level')
        if 'passenger_class' in entities: entities['class'] = entities.pop('passenger_class')

        # ------------------------------------------
        # 1. INTENT: search_network
        # ------------------------------------------
        if intent == "search_network":
            # CASE: Specific Long Haul Route (Origin + Dest + Min Miles)
            # Fixes: "Find all flights from JNX to EWX longer than 2000 miles"
            if 'origin' in entities and 'dest' in entities and 'min_miles' in entities:
                return """
                    MATCH (origin:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(dest:Airport {station_code: $dest})
                    MATCH (j:Journey)-[:ON]->(f)
                    WHERE j.actual_flown_miles > $min_miles
                    RETURN DISTINCT f.flight_number, 
                                    f.fleet_type_description, 
                                    j.actual_flown_miles
                """

            # CASE: Standard Route Lookup (Origin + Dest)
            if 'origin' in entities and 'dest' in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    RETURN f.flight_number, f.fleet_type_description
                """

            # CASE: Frequency from Origin
            if 'origin' in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport)
                    RETURN o.station_code AS origin, 
                           d.station_code AS destination, 
                           count(f) AS flight_options_count
                    ORDER BY flight_options_count DESC
                    LIMIT 10
                """

        # ------------------------------------------
        # 2. INTENT: analyze_satisfaction
        # ------------------------------------------
        if intent == "analyze_satisfaction":
            # CASE: Loyalty Tier + Cabin Class
            # Fixes: "Average satisfaction for Premier Gold members in Economy?"
            if 'loyalty_tier' in entities and 'class' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.loyalty_program_level = $loyalty_tier 
                      AND j.passenger_class = $class
                    RETURN avg(j.food_satisfaction_score) AS average_rating, 
                           count(j) AS total_trips
                """

            # CASE: Generation + Fleet Type
            # Fixes: "Gen X passengers on A320-200" (Moved from analyze_issues to here for robustness)
            if 'generation' in entities and 'fleet_type' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE p.generation = $generation 
                      AND f.fleet_type_description = $fleet_type
                    RETURN p.generation, f.fleet_type_description,
                           avg(j.food_satisfaction_score) AS average_food_rating
                """

            # CASE: Generation Only
            if 'generation' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.generation = $generation
                    RETURN p.generation AS generation, 
                           avg(j.food_satisfaction_score) AS average_food_rating
                """
            
            # Default Global Average
            return "MATCH (j:Journey) RETURN avg(j.food_satisfaction_score) as global_avg"

        # ------------------------------------------
        # 3. INTENT: analyze_delays
        # ------------------------------------------
        if intent == "analyze_delays":
            # CASE: Specific Airport
            # Fixes: "Show me the delay statistics for flights out of JNX."
            if 'origin' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport {station_code: $origin})
                    RETURN a.station_code AS airport, 
                           min(j.arrival_delay_minutes) AS min_delay, 
                           max(j.arrival_delay_minutes) AS max_delay, 
                           avg(j.arrival_delay_minutes) AS avg_delay
                """
            
            # Default: Fleet Ranking
            return """
                MATCH (j:Journey)-[:ON]->(f:Flight)
                RETURN f.fleet_type_description AS aircraft_type, 
                       avg(j.arrival_delay_minutes) AS average_delay
                ORDER BY average_delay DESC
                LIMIT 5
            """

        # ------------------------------------------
        # 4. INTENT: analyze_issues (Complex Filters)
        # ------------------------------------------
        if intent == "analyze_issues":
            # CASE: Severe Delays + Poor Ratings
            if 'min_delay' in entities and 'max_score' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.arrival_delay_minutes > $min_delay 
                      AND j.food_satisfaction_score <= $max_score
                    RETURN f.flight_number, 
                           j.arrival_delay_minutes, 
                           j.food_satisfaction_score, 
                           j.feedback_ID
                    LIMIT 20
                """

        # ------------------------------------------
        # 5. INTENT: lookup_details
        # ------------------------------------------
        if intent == "lookup_details":
            # CASE: Record Locator (handles 'vip_id' via normalization at top)
            # Fixes: "Pull up record for locator EPXXW8"
            if 'record_locator' in entities:
                return """
                    MATCH (p:Passenger {record_locator: $record_locator})-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    RETURN p, j, f
                """

            if 'feedback_id' in entities:
                return """
                    MATCH (j:Journey {feedback_ID: $feedback_id})
                    OPTIONAL MATCH (p:Passenger)-[:TOOK]->(j)-[:ON]->(f:Flight)
                    RETURN properties(j) AS journey_details, 
                           properties(p) AS passenger_details, 
                           f.flight_number
                """

        return None

    def run_query(self, intent, entities):
        # Clean entities (remove Nones)
        clean_params = {k: v for k, v in entities.items() if v is not None}
        
        # Get query with Normalized parameters
        cypher_query = self.get_query_for_intent(intent, clean_params)
        
        if not cypher_query:
            return f"Error: Could not construct query for intent '{intent}' with entities {list(clean_params.keys())}"

        try:
            if self.driver is None:
                return "Database Error: Driver not initialized."
            
            # Debug Print
            print(f"\n--- Executing Query ---")
            print(f"Intent: {intent}")
            print(f"Parameters: {clean_params}")
            print(f"Cypher Query:\n{cypher_query}")
            print(f"--- End Query ---\n")
            
            records, summary, keys = self.driver.execute_query(
                cypher_query,
                clean_params,
                database_="neo4j", 
            )
            return [dict(record) for record in records]

        except Exception as e:
            return f"Database Error: {e}"

# --- Usage Example ---
if __name__ == "__main__":
    retriever = Neo4jRetriever()
    
    print("\n--- TEST 1: Long Haul Route (Case 1 Fix) ---")
    print(retriever.run_query("search_network", {'origin': 'JNX', 'dest': 'EWX', 'min_miles': 2000}))

    print("\n--- TEST 2: Loyalty + Class (Case 2 Fix) ---")
    print(retriever.run_query("analyze_satisfaction", {'loyalty_level': 'Premier Gold', 'passenger_class': 'Economy'}))

    print("\n--- TEST 3: Gen X + Fleet (Case 3 Fix) ---")
    print(retriever.run_query("analyze_satisfaction", {'generation': 'Gen X', 'fleet_type': 'A320-200'}))

    print("\n--- TEST 4: Record Locator (Case 4 Fix) ---")
    print(retriever.run_query("lookup_details", {'vip_id': 'EPXXW8'}))
    
    print("\n--- TEST 5: JNX Delays (Case 5 Fix) ---")
    print(retriever.run_query("analyze_delays", {'origin': 'JNX'}))