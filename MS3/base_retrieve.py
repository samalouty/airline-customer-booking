from neo4j import GraphDatabase
import os

# --- Configuration ---
URI = "bolt://localhost:7687"
AUTH = ("neo4j", "password") # Update with your credentials

# --- 1:1 Intent to Cypher Map ---
CYPHER_TEMPLATES = {
    # 1. Operational Efficiency
    "analyze_fleet_delays": """
        MATCH (j:Journey)-[:ON]->(f:Flight)
        RETURN f.fleet_type_description AS aircraft_type, 
               avg(j.arrival_delay_minutes) AS average_delay
        ORDER BY average_delay DESC LIMIT 5
    """,
    
    "analyze_airport_delays": """
        MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport {station_code: $origin_code})
        RETURN a.station_code AS airport, 
               min(j.arrival_delay_minutes) AS min_delay, 
               max(j.arrival_delay_minutes) AS max_delay, 
               avg(j.arrival_delay_minutes) AS avg_delay
    """,

    # 2. Customer Experience
    "analyze_generational_satisfaction": """
        MATCH (p:Passenger)-[:TOOK]->(j:Journey)
        WHERE p.generation = $generation
        RETURN p.generation AS generation, 
               avg(j.food_satisfaction_score) AS average_food_rating
    """,

    "analyze_loyalty_rating": """
        MATCH (p:Passenger)-[:TOOK]->(j:Journey)
        WHERE p.loyalty_program_level = $loyalty_tier AND j.passenger_class = $cabin_class
        RETURN avg(j.food_satisfaction_score) AS average_rating, 
               count(j) AS total_trips
    """,

    # 3. Network & Routes
    "find_long_haul_flights": """
        MATCH (origin:Airport {station_code: $origin_code})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(dest:Airport {station_code: $dest_code})
        MATCH (j:Journey)-[:ON]->(f)
        WHERE j.actual_flown_miles > $min_miles
        RETURN DISTINCT f.flight_number, f.fleet_type_description, j.actual_flown_miles
    """,

    "analyze_route_frequency": """
        MATCH (o:Airport {station_code: $origin_code})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport)
        RETURN o.station_code AS origin, d.station_code AS destination, count(f) AS flight_options_count
        ORDER BY flight_options_count DESC LIMIT 10
    """,

    # 4. Semantic / Complex
    "find_severe_service_issues": """
        MATCH (j:Journey)-[:ON]->(f:Flight)
        WHERE j.arrival_delay_minutes > $min_delay 
          AND j.food_satisfaction_score <= $max_score
        RETURN f.flight_number, j.arrival_delay_minutes, j.food_satisfaction_score, j.feedback_ID
        LIMIT 20
    """,

    "analyze_demographic_on_fleet": """
        MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
        WHERE p.generation = $generation 
          AND f.fleet_type_description = $aircraft_type
        RETURN j.food_satisfaction_score, j.arrival_delay_minutes, p.loyalty_program_level
        LIMIT 50
    """,

    # 5. Lookup
    "lookup_passenger_record": """
        MATCH (p:Passenger {record_locator: $record_locator})-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
        RETURN properties(p) as passenger, properties(j) as journey, properties(f) as flight
    """,

    "lookup_feedback_details": """
        MATCH (j:Journey {feedback_ID: $feedback_id})
        OPTIONAL MATCH (p:Passenger)-[:TOOK]->(j)-[:ON]->(f:Flight)
        RETURN properties(j) AS journey_details, properties(p) AS passenger_details, f.flight_number
    """
}

def run_query(intent, entities):
    """
    Selects the correct template and executes it against Neo4j.
    """
    if intent not in CYPHER_TEMPLATES:
        return f"Error: No template found for intent '{intent}'"
    
    query = CYPHER_TEMPLATES[intent]
    
    # Connect to Neo4j
    try:
        with GraphDatabase.driver(URI, auth=AUTH) as driver:
            records, summary, keys = driver.execute_query(
                query,
                entities, # Pass the dictionary directly as parameters
                database_="neo4j", 
            )
            
            # Format results nicely for the LLM Context
            results = [dict(record) for record in records]
            return results

    except Exception as e:
        return f"Database Error: {e}"

# --- Main Pipeline Integration ---
if __name__ == "__main__":
    # Simulate data coming from preprocess.py
    # Example: User asked "Find severe delays > 60 mins with rating < 2"
    processed_input = {
        "intent": "find_severe_service_issues",
        "entities": {"min_delay": 60, "max_score": 2}
    }
    
    print(f"Executing Intent: {processed_input['intent']}...")
    graph_data = run_query(processed_input['intent'], processed_input['entities'])
    
    print("--- Graph Results ---")
    print(graph_data)