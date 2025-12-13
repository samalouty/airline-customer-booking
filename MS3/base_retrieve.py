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
            "lookup_details",
            "analyze_passengers",
            "analyze_journeys",
            "compare_routes",
            "analyze_loyalty",
            "analyze_experience"
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
        
        # --- Fix 3: Normalize loyalty tier format ---
        if 'loyalty_tier' in clean:
            tier = clean['loyalty_tier'].lower()
            if 'premier gold' in tier or 'gold' in tier: clean['loyalty_tier'] = 'premier gold'
            elif 'premier silver' in tier or 'silver' in tier: clean['loyalty_tier'] = 'premier silver'
            elif 'premier platinum' in tier or 'platinum' in tier: clean['loyalty_tier'] = 'premier platinum'
            elif 'premier 1k' in tier or '1k' in tier: clean['loyalty_tier'] = 'premier 1k'
            elif 'non-elite' in tier or 'non elite' in tier: clean['loyalty_tier'] = 'non-elite'

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
            # Route search with delay filters
            if 'origin' in entities and 'dest' in entities and 'min_delay' in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    MATCH (j:Journey)-[:ON]->(f)
                    WHERE j.arrival_delay_minutes >= $min_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            if 'origin' in entities and 'dest' in entities and 'max_delay' in entities:
                return """
                    MATCH (o:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    MATCH (j:Journey)-[:ON]->(f)
                    WHERE j.arrival_delay_minutes <= $max_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes LIMIT 20
                """
            # Route search with mileage range
            if 'origin' in entities and 'dest' in entities and 'min_miles' in entities and 'max_miles' in entities:
                return """
                    MATCH (origin:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(dest:Airport {station_code: $dest})
                    MATCH (j:Journey)-[:ON]->(f)
                    WHERE j.actual_flown_miles >= $min_miles AND j.actual_flown_miles <= $max_miles
                    RETURN DISTINCT f.flight_number, f.fleet_type_description, j.actual_flown_miles
                """
            if 'origin' in entities and 'dest' in entities and 'min_miles' in entities:
                return """
                    MATCH (origin:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(dest:Airport {station_code: $dest})
                    MATCH (j:Journey)-[:ON]->(f)
                    WHERE j.actual_flown_miles > $min_miles
                    RETURN DISTINCT f.flight_number, f.fleet_type_description, j.actual_flown_miles
                """
            if 'origin' in entities and 'dest' in entities and 'max_miles' in entities:
                return """
                    MATCH (origin:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(dest:Airport {station_code: $dest})
                    MATCH (j:Journey)-[:ON]->(f)
                    WHERE j.actual_flown_miles < $max_miles
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
            if 'dest' in entities:
                return """
                    MATCH (o:Airport)<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    RETURN o.station_code AS origin, d.station_code AS destination, count(f) AS flight_options_count
                    ORDER BY flight_options_count DESC LIMIT 10
                """
            # Search by mileage only (no specific route)
            if 'min_miles' in entities and 'max_miles' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport)
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport)
                    WHERE j.actual_flown_miles >= $min_miles AND j.actual_flown_miles <= $max_miles
                    RETURN DISTINCT o.station_code AS origin, d.station_code AS destination,
                           f.flight_number, f.fleet_type_description, j.actual_flown_miles
                    ORDER BY j.actual_flown_miles DESC LIMIT 20
                """
            if 'min_miles' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport)
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport)
                    WHERE j.actual_flown_miles >= $min_miles
                    RETURN DISTINCT o.station_code AS origin, d.station_code AS destination,
                           f.flight_number, f.fleet_type_description, j.actual_flown_miles
                    ORDER BY j.actual_flown_miles DESC LIMIT 20
                """
            if 'max_miles' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport)
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport)
                    WHERE j.actual_flown_miles <= $max_miles
                    RETURN DISTINCT o.station_code AS origin, d.station_code AS destination,
                           f.flight_number, f.fleet_type_description, j.actual_flown_miles
                    ORDER BY j.actual_flown_miles LIMIT 20
                """

        # 2. INTENT: analyze_satisfaction
        if intent == "analyze_satisfaction":
            # Satisfaction with food score range
            if 'loyalty_tier' in entities and 'class' in entities and 'min_food_satisfaction' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.loyalty_program_level = $loyalty_tier AND j.passenger_class = $class
                      AND j.food_satisfaction_score >= $min_food_satisfaction
                    RETURN avg(j.food_satisfaction_score) AS average_rating, count(j) AS total_trips
                """
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
            if 'generation' in entities and 'min_food_satisfaction' in entities and 'max_food_satisfaction' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.generation = $generation
                      AND j.food_satisfaction_score >= $min_food_satisfaction
                      AND j.food_satisfaction_score <= $max_food_satisfaction
                    RETURN p.generation AS generation, j.food_satisfaction_score, count(j) AS count
                    ORDER BY j.food_satisfaction_score
                """
            if 'generation' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.generation = $generation
                    RETURN p.generation AS generation, avg(j.food_satisfaction_score) AS average_food_rating
                """
            if 'loyalty_tier' in entities: 
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.loyalty_program_level = $loyalty_tier
                    RETURN p.loyalty_program_level AS loyalty_tier, avg(j.food_satisfaction_score) AS average_food_rating
                """
            
            if 'min_food_satisfaction' in entities and 'max_food_satisfaction' in entities:
                return """
                    MATCH (j:Journey)
                    WHERE j.food_satisfaction_score >= $min_food_satisfaction 
                      AND j.food_satisfaction_score <= $max_food_satisfaction
                    RETURN j.food_satisfaction_score AS score, count(j) AS journey_count
                    ORDER BY score
                """
            if 'max_food_satisfaction' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.food_satisfaction_score <= $max_food_satisfaction
                    RETURN f.flight_number, j.food_satisfaction_score, p.generation, j.feedback_ID
                    ORDER BY j.food_satisfaction_score LIMIT 20
                """
            return "MATCH (j:Journey) RETURN avg(j.food_satisfaction_score) as global_avg"

        # 3. INTENT: analyze_delays
        if intent == "analyze_delays":
            # Delays for specific route with delay range
            if 'origin' in entities and 'dest' in entities and 'min_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport {station_code: $origin})
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    WHERE j.arrival_delay_minutes >= $min_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            if 'origin' in entities and 'dest' in entities and 'max_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport {station_code: $origin})
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    WHERE j.arrival_delay_minutes <= $max_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes LIMIT 20
                """
            if 'origin' in entities and 'dest' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport {station_code: $origin})
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    RETURN f.flight_number, min(j.arrival_delay_minutes) AS min_delay, 
                           max(j.arrival_delay_minutes) AS max_delay, avg(j.arrival_delay_minutes) AS avg_delay
                """
            # Delays with min_delay and max_delay range
            if 'min_delay' in entities and 'max_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.arrival_delay_minutes >= $min_delay AND j.arrival_delay_minutes <= $max_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            if 'min_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.arrival_delay_minutes >= $min_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            if 'max_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.arrival_delay_minutes <= $max_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes LIMIT 20
                """
            # Origin with delay filter
            if 'origin' in entities and 'min_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport {station_code: $origin})
                    WHERE j.arrival_delay_minutes >= $min_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID, a.station_code AS origin
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            if 'origin' in entities and 'max_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport {station_code: $origin})
                    WHERE j.arrival_delay_minutes <= $max_delay
                    RETURN f.flight_number, f.fleet_type_description, j.arrival_delay_minutes, j.feedback_ID, a.station_code AS origin
                    ORDER BY j.arrival_delay_minutes LIMIT 20
                """
            if 'origin' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport {station_code: $origin})
                    RETURN a.station_code AS airport, min(j.arrival_delay_minutes) AS min_delay, max(j.arrival_delay_minutes) AS max_delay, avg(j.arrival_delay_minutes) AS avg_delay
                """
            if 'fleet_type' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE f.fleet_type_description CONTAINS $fleet_type
                    RETURN f.fleet_type_description AS aircraft_type, 
                           min(j.arrival_delay_minutes) AS min_delay,
                           max(j.arrival_delay_minutes) AS max_delay,
                           avg(j.arrival_delay_minutes) AS average_delay
                """
            return """
                MATCH (j:Journey)-[:ON]->(f:Flight)
                RETURN f.fleet_type_description AS aircraft_type, avg(j.arrival_delay_minutes) AS average_delay
                ORDER BY average_delay DESC LIMIT 5
            """

        # 4. INTENT: analyze_issues
        if intent == "analyze_issues":
            # Issues with delay and satisfaction constraints
            if 'min_delay' in entities and 'max_food_satisfaction' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.arrival_delay_minutes >= $min_delay AND j.food_satisfaction_score <= $max_food_satisfaction
                    RETURN f.flight_number, j.arrival_delay_minutes, j.food_satisfaction_score, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            if 'min_delay' in entities and 'max_score' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.arrival_delay_minutes > $min_delay AND j.food_satisfaction_score <= $max_score
                    RETURN f.flight_number, j.arrival_delay_minutes, j.food_satisfaction_score, j.feedback_ID
                    LIMIT 20
                """
            # Issues for specific route
            if 'origin' in entities and 'dest' in entities and 'min_delay' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport {station_code: $origin})
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    WHERE j.arrival_delay_minutes >= $min_delay
                    RETURN f.flight_number, j.arrival_delay_minutes, j.food_satisfaction_score, j.feedback_ID, j.passenger_class
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            # Issues with multi-leg journeys
            if 'min_legs' in entities and 'min_delay' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.number_of_legs >= $min_legs AND j.arrival_delay_minutes >= $min_delay
                    RETURN p.record_locator, f.flight_number, j.number_of_legs, j.arrival_delay_minutes, j.feedback_ID
                    ORDER BY j.arrival_delay_minutes DESC LIMIT 20
                """
            if 'max_food_satisfaction' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)
                    WHERE j.food_satisfaction_score <= $max_food_satisfaction
                    RETURN f.flight_number, j.arrival_delay_minutes, j.food_satisfaction_score, j.feedback_ID
                    ORDER BY j.food_satisfaction_score LIMIT 20
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

        # 6. INTENT: analyze_passengers
        if intent == "analyze_passengers":
            # Passengers by loyalty tier with journey stats
            if 'loyalty_tier' in entities and 'min_miles' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.loyalty_program_level = $loyalty_tier AND j.actual_flown_miles >= $min_miles
                    RETURN p.record_locator, p.loyalty_program_level, p.generation,
                           count(j) AS total_journeys, sum(j.actual_flown_miles) AS total_miles
                    ORDER BY total_miles DESC LIMIT 20
                """
            if 'loyalty_tier' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.loyalty_program_level = $loyalty_tier
                    RETURN p.record_locator, p.generation, count(j) AS journey_count,
                           avg(j.food_satisfaction_score) AS avg_satisfaction
                    ORDER BY journey_count DESC LIMIT 20
                """
            if 'generation' in entities and 'loyalty_tier' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.generation = $generation AND p.loyalty_program_level = $loyalty_tier
                    RETURN p.record_locator, count(j) AS journey_count, 
                           sum(j.actual_flown_miles) AS total_miles,
                           avg(j.food_satisfaction_score) AS avg_satisfaction
                    ORDER BY total_miles DESC LIMIT 20
                """
            if 'generation' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.generation = $generation
                    RETURN p.loyalty_program_level AS loyalty_tier, count(DISTINCT p) AS passenger_count,
                           avg(j.food_satisfaction_score) AS avg_satisfaction
                    ORDER BY passenger_count DESC
                """
            # Passengers with frequent delays
            if 'min_delay' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE j.arrival_delay_minutes >= $min_delay
                    RETURN p.record_locator, p.generation, p.loyalty_program_level,
                           count(j) AS delayed_journeys, avg(j.arrival_delay_minutes) AS avg_delay
                    ORDER BY delayed_journeys DESC LIMIT 20
                """
            # Default: passenger distribution by generation
            return """
                MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                RETURN p.generation AS generation, p.loyalty_program_level AS loyalty_tier,
                       count(DISTINCT p) AS passenger_count
                ORDER BY passenger_count DESC
            """

        # 6b. INTENT: analyze_loyalty (for loyalty-specific questions)
        if intent == "analyze_loyalty":
            # Most common loyalty level
            if 'loyalty_tier' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE p.loyalty_program_level = $loyalty_tier
                    RETURN p.loyalty_program_level AS loyalty_tier,
                           count(DISTINCT p) AS passenger_count,
                           avg(j.food_satisfaction_score) AS avg_food_satisfaction,
                           avg(j.arrival_delay_minutes) AS avg_delay,
                           avg(j.actual_flown_miles) AS avg_miles
                """
            # Default: loyalty tier distribution and stats
            return """
                MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                RETURN p.loyalty_program_level AS loyalty_tier,
                       count(DISTINCT p) AS passenger_count,
                       avg(j.food_satisfaction_score) AS avg_food_satisfaction,
                       avg(j.arrival_delay_minutes) AS avg_delay
                ORDER BY passenger_count DESC
            """

        # 6c. INTENT: analyze_experience (for average experience questions)
        if intent == "analyze_experience":
            # Experience by loyalty tier
            if 'loyalty_tier' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE p.loyalty_program_level = $loyalty_tier
                    RETURN p.loyalty_program_level AS loyalty_tier,
                           count(j) AS total_journeys,
                           avg(j.food_satisfaction_score) AS avg_food_satisfaction,
                           avg(j.arrival_delay_minutes) AS avg_delay_minutes,
                           avg(j.actual_flown_miles) AS avg_miles,
                           avg(j.number_of_legs) AS avg_legs
                """
            # Experience by generation
            if 'generation' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE p.generation = $generation
                    RETURN p.generation AS generation,
                           count(j) AS total_journeys,
                           avg(j.food_satisfaction_score) AS avg_food_satisfaction,
                           avg(j.arrival_delay_minutes) AS avg_delay_minutes,
                           avg(j.actual_flown_miles) AS avg_miles
                """
            # Experience by class
            if 'class' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE j.passenger_class = $class
                    RETURN j.passenger_class AS class,
                           count(j) AS total_journeys,
                           avg(j.food_satisfaction_score) AS avg_food_satisfaction,
                           avg(j.arrival_delay_minutes) AS avg_delay_minutes,
                           avg(j.actual_flown_miles) AS avg_miles
                """
            # Default: overall experience stats
            return """
                MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                RETURN p.loyalty_program_level AS loyalty_tier,
                       count(j) AS total_journeys,
                       avg(j.food_satisfaction_score) AS avg_food_satisfaction,
                       avg(j.arrival_delay_minutes) AS avg_delay_minutes,
                       avg(j.actual_flown_miles) AS avg_miles
                ORDER BY total_journeys DESC
            """

        # 7. INTENT: analyze_journeys
        if intent == "analyze_journeys":
            # Journeys with leg constraints
            if 'min_legs' in entities and 'max_legs' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.number_of_legs >= $min_legs AND j.number_of_legs <= $max_legs
                    RETURN j.feedback_ID, j.number_of_legs, j.actual_flown_miles, 
                           j.arrival_delay_minutes, j.food_satisfaction_score,
                           p.record_locator, f.flight_number
                    ORDER BY j.number_of_legs DESC LIMIT 20
                """
            if 'min_legs' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.number_of_legs >= $min_legs
                    RETURN j.feedback_ID, j.number_of_legs, j.actual_flown_miles,
                           j.arrival_delay_minutes, j.food_satisfaction_score,
                           p.record_locator, f.flight_number
                    ORDER BY j.number_of_legs DESC LIMIT 20
                """
            if 'max_legs' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.number_of_legs <= $max_legs
                    RETURN j.feedback_ID, j.number_of_legs, j.actual_flown_miles,
                           j.arrival_delay_minutes, j.food_satisfaction_score,
                           p.record_locator, f.flight_number
                    ORDER BY j.number_of_legs LIMIT 20
                """
            # Journeys with mileage range
            if 'min_miles' in entities and 'max_miles' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.actual_flown_miles >= $min_miles AND j.actual_flown_miles <= $max_miles
                    RETURN j.feedback_ID, j.actual_flown_miles, j.number_of_legs,
                           j.food_satisfaction_score, f.fleet_type_description
                    ORDER BY j.actual_flown_miles DESC LIMIT 20
                """
            if 'min_miles' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.actual_flown_miles >= $min_miles
                    RETURN j.feedback_ID, j.actual_flown_miles, j.number_of_legs,
                           j.food_satisfaction_score, p.generation, f.fleet_type_description
                    ORDER BY j.actual_flown_miles DESC LIMIT 20
                """
            if 'max_miles' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
                    WHERE j.actual_flown_miles <= $max_miles
                    RETURN j.feedback_ID, j.actual_flown_miles, j.number_of_legs,
                           j.food_satisfaction_score, p.generation, f.fleet_type_description
                    ORDER BY j.actual_flown_miles LIMIT 20
                """
            # Journeys by class with satisfaction
            if 'class' in entities:
                return """
                    MATCH (p:Passenger)-[:TOOK]->(j:Journey)
                    WHERE j.passenger_class = $class
                    RETURN j.passenger_class, count(j) AS journey_count,
                           avg(j.food_satisfaction_score) AS avg_food_score,
                           avg(j.arrival_delay_minutes) AS avg_delay
                """
            # Default: journey statistics by class
            return """
                MATCH (j:Journey)
                RETURN j.passenger_class AS class, count(j) AS journey_count,
                       avg(j.food_satisfaction_score) AS avg_satisfaction,
                       avg(j.arrival_delay_minutes) AS avg_delay,
                       avg(j.actual_flown_miles) AS avg_miles
                ORDER BY journey_count DESC
            """

        # 8. INTENT: compare_routes
        if intent == "compare_routes":
            if 'origin' in entities and 'dest' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport {station_code: $origin})
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport {station_code: $dest})
                    RETURN f.fleet_type_description AS aircraft,
                           count(j) AS flight_count,
                           avg(j.arrival_delay_minutes) AS avg_delay,
                           avg(j.food_satisfaction_score) AS avg_food_score,
                           avg(j.actual_flown_miles) AS avg_miles
                    ORDER BY flight_count DESC
                """
            if 'origin' in entities:
                return """
                    MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport {station_code: $origin})
                    MATCH (f)-[:ARRIVES_AT]->(d:Airport)
                    RETURN d.station_code AS destination,
                           count(j) AS flight_count,
                           avg(j.arrival_delay_minutes) AS avg_delay,
                           avg(j.food_satisfaction_score) AS avg_food_score
                    ORDER BY flight_count DESC LIMIT 10
                """
            return None

        return None

    def run_query(self, intent, entities):
        # 1. Normalize Entities (Fixes 'Boomers' -> 'Boomer')
        clean_params = self.normalize_entities(entities)
        clean_params = {k: v for k, v in clean_params.items() if v is not None}
        
        # 2. Get Query
        cypher_query = self.get_query_for_intent(intent, clean_params)
        
        if not cypher_query:
            return f"Error: Could not construct query for intent '{intent}' with entities {list(clean_params.keys())}", None

        try:
            if self.driver is None:
                return "Database Error: Driver not initialized.", None
            
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

            return serialized_results, cypher_query

        except Exception as e:
            return f"Database Error: {e}", None

# --- Usage Example ---
if __name__ == "__main__":
    retriever = Neo4jRetriever()
    
    print("\n--- TEST 1: Boomers Plural Fix ---")
    # Input 'Boomers' -> Should convert to 'Boomer' and find results
    results, query = retriever.run_query("analyze_satisfaction", {'generation': 'Boomers'})
    print(results)

    print("\n--- TEST 2: Record Lookup Clean Output Fix ---")
    # Should output clean JSON, not <Node ...>
    results, query = retriever.run_query("lookup_details", {'vip_id': 'EPXXW8'})
    print(results)