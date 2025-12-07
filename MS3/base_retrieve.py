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

    # ==========================================
    # Available Intents
    # ==========================================
    def get_available_intents(self):
        """
        Returns a list of all available intents that the system can handle.
        """
        return [
            "analyze_satisfaction",
            "analyze_delays",
            "search_network",
            "lookup_details"
        ]

    # ==========================================
    # LOGIC: The Internal Router
    # ==========================================
    def get_query_for_intent(self, intent, entities):
        """
        Maps a Broad Intent + Available Entities -> Specific Cypher Query
        """
        
        # ------------------------------------------
        # 1. INTENT: analyze_satisfaction (CX)
        # ------------------------------------------
        if intent == "analyze_satisfaction":
            # If user mentions a Generation (e.g. "Do Millennials like the food?")
            if "generation" in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
                    WHERE p.generation = $generation
                    RETURN p.generation, avg(j.food_satisfaction_score) as avg_score
                """
            
            # If user mentions Loyalty (e.g. "Do Gold members like the food?")
            elif "loyalty_level" in entities:
                return """
                    MATCH (p:Passenger {loyalty_program_level: $loyalty_level})-[:TOOK]->(j:Journey) 
                    RETURN p.loyalty_program_level, avg(j.food_satisfaction_score) as avg_score
                """

            # If user mentions Fleet (e.g. "Food rating on Boeing 777")
            elif "fleet_type" in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE f.fleet_type_description CONTAINS $fleet_type
                    RETURN f.fleet_type_description, avg(j.food_satisfaction_score) as score
                """

            # Default: Global Average
            else:
                return "MATCH (j:Journey) RETURN avg(j.food_satisfaction_score) as Global_Avg_Food_Score"

        # ------------------------------------------
        # 2. INTENT: analyze_delays (Ops)
        # ------------------------------------------
        if intent == "analyze_delays":
            # Specific Airport Delay
            if "origin" in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport {station_code: $origin}) 
                    RETURN a.station_code, avg(j.arrival_delay_minutes) as avg_delay, max(j.arrival_delay_minutes) as max_delay
                """
            
            # Specific Fleet Delay
            elif "fleet_type" in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight) 
                    WHERE f.fleet_type_description CONTAINS $fleet_type
                    RETURN f.fleet_type_description, avg(j.arrival_delay_minutes) as avg_delay
                """

            # Default: Worst Performing Fleet
            else:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight) 
                    RETURN f.fleet_type_description, avg(j.arrival_delay_minutes) as avg_delay
                    ORDER BY avg_delay DESC LIMIT 5
                """

        # ------------------------------------------
        # 3. INTENT: search_network (Routes)
        # ------------------------------------------
        if intent == "search_network":
            # A to B (Specific Route)
            if "origin" in entities and "dest" in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    RETURN f.flight_number, f.fleet_type_description
                """
            
            # From A (Outgoing)
            elif "origin" in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport)
                    RETURN d.station_code as Destination, count(f) as Flight_Frequency
                    ORDER BY Flight_Frequency DESC
                """
            
            # To B (Incoming)
            elif "dest" in entities:
                return """
                    MATCH (o:Airport)<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    RETURN o.station_code as Origin, count(f) as Flight_Frequency
                    ORDER BY Flight_Frequency DESC
                """

        # ------------------------------------------
        # 4. INTENT: lookup_details
        # ------------------------------------------
        if intent == "lookup_details":
            if "record_locator" in entities:
                return "MATCH (p:Passenger {record_locator: $record_locator})-[:TOOK]->(j) RETURN p, j"
            if "feedback_id" in entities:
                return "MATCH (j:Journey {feedback_ID: $feedback_id}) RETURN j"

        return None


    def run_query(self, intent, entities):
        """
        Executes the logic.
        """
        # 1. Get the dynamic Cypher string
        cypher_query = self.get_query_for_intent(intent, entities)
        
        if not cypher_query:
            return f"Error: Could not construct query for intent '{intent}' with entities {list(entities.keys())}"

        # 2. Execute
        try:
            if self.driver is None:
                return "Database Error: Driver not initialized."

            # Clean up entities (remove None values so Neo4j doesn't complain)
            clean_params = {k: v for k, v in entities.items() if v is not None}

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
    
    # Example 1: "How is the food on B777?"
    # LLM Output: Intent='analyze_satisfaction', Entities={'fleet_type': 'B777'}
    print(retriever.run_query("analyze_satisfaction", {"fleet_type": "B777"}))

    # Example 2: "Flights from ORD"
    # LLM Output: Intent='search_network', Entities={'origin': 'ORD'}
    print(retriever.run_query("search_network", {"origin": "ORD"}))
    
    # Example 3: "Flights from ORD to LAX"
    # LLM Output: Intent='search_network', Entities={'origin': 'ORD', 'dest': 'LAX'}
    print(retriever.run_query("search_network", {"origin": "ORD", "dest": "LAX"}))