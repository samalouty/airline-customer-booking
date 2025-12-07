#!/usr/bin/env python3
from neo4j import GraphDatabase
import os
import sys

# --- Configuration ---
# Add the project root to the python path so we can import config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.neo4j_client import driver as default_driver

class Neo4jRetriever:
    """
    Handles retrieval of data from Neo4j using predefined Cypher templates.
    """
    
    # --- 1:1 Intent to Cypher Map (100 Queries) ---
    CYPHER_TEMPLATES = {
        # =========================================================
        # 1. CUSTOMER EXPERIENCE (CX) & SATISFACTION
        # =========================================================

        "analytics.cx.global_avg": """
            MATCH (j:Journey) 
            RETURN avg(j.food_satisfaction_score) as Global_Avg_Food_Score
        """,

        "analytics.cx.by_class": """
            MATCH (j:Journey) 
            RETURN j.passenger_class, avg(j.food_satisfaction_score) as avg_score 
            ORDER BY avg_score DESC
        """,

        "analytics.cx.correlation_delay": """
            MATCH (j:Journey) 
            WITH j.arrival_delay_minutes > $min_delay AS is_delayed, avg(j.food_satisfaction_score) as avg_score 
            RETURN is_delayed, avg_score
        """,

        "analytics.cx.fleet_ranking_top": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, avg(j.food_satisfaction_score) as score 
            ORDER BY score DESC LIMIT 1
        """,

        "analytics.cx.fleet_ranking_bottom": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, avg(j.food_satisfaction_score) as score 
            ORDER BY score ASC LIMIT 1
        """,

        "analytics.cx.by_generation": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            RETURN p.generation, avg(j.food_satisfaction_score) as avg_score
        """,

        "analytics.cx.by_loyalty_tier": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            RETURN p.loyalty_program_level, avg(j.food_satisfaction_score) as avg_score
        """,

        "analytics.cx.correlation_legs": """
            MATCH (j:Journey) 
            RETURN j.number_of_legs, avg(j.food_satisfaction_score) as avg_score 
            ORDER BY j.number_of_legs
        """,

        "analytics.cx.dest_ranking": """
            MATCH (j:Journey)-[:ON]->(f:Flight)-[:ARRIVES_AT]->(a:Airport) 
            RETURN a.station_code, avg(j.food_satisfaction_score) as score 
            ORDER BY score DESC LIMIT 1
        """,

        "analytics.cx.origin_ranking": """
            MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport) 
            RETURN a.station_code, avg(j.food_satisfaction_score) as score 
            ORDER BY score ASC LIMIT 1
        """,

        "analytics.cx.correlation_distance": """
            MATCH (j:Journey) 
            RETURN CASE WHEN j.actual_flown_miles > 2000 THEN 'Long-Haul' ELSE 'Short-Haul' END as type, 
                   avg(j.food_satisfaction_score) as avg_score
        """,

        "analytics.cx.score_distribution": """
            MATCH (j:Journey) 
            RETURN j.food_satisfaction_score, count(*) as freq 
            ORDER BY j.food_satisfaction_score
        """,

        "analytics.cx.flight_outliers": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WHERE j.food_satisfaction_score < $max_score 
            RETURN f.flight_number, count(*) as poor_feedback_count 
            ORDER BY poor_feedback_count DESC
        """,

        "analytics.cx.feedback_volume": """
            MATCH (j:Journey) 
            RETURN j.passenger_class, count(j.feedback_ID) as feedback_count
        """,

        "analytics.cx.freq_flyer_bias": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WITH p, count(j) as flight_count, avg(j.food_satisfaction_score) as avg_score 
            RETURN flight_count, avg_score 
            ORDER BY flight_count DESC
        """,

        "analytics.cx.perfect_score_metric": """
            MATCH (j:Journey) 
            WHERE j.food_satisfaction_score >= $min_score 
            RETURN percentileDisc(j.arrival_delay_minutes, 0.5) as Median_Delay
        """,

        "analytics.cx.route_ranking": """
            MATCH (origin:Airport)<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(dest:Airport), (j:Journey)-[:ON]->(f) 
            RETURN origin.station_code, dest.station_code, avg(j.food_satisfaction_score) as score 
            ORDER BY score DESC LIMIT 1
        """,

        "analytics.cx.factor_comparison": """
            MATCH (j:Journey) 
            RETURN corr(j.number_of_legs, j.food_satisfaction_score) as Leg_Corr, 
                   corr(j.arrival_delay_minutes, j.food_satisfaction_score) as Delay_Corr
        """,

        "analytics.cx.specific_segment": """
            MATCH (p:Passenger {generation: $generation})-[:TOOK]->(j:Journey {passenger_class: $passenger_class}) 
            RETURN avg(j.food_satisfaction_score) as avg_score
        """,

        "analytics.cx.fleet_failure_rate": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WITH f.fleet_type_description as fleet, count(j) as total, 
                 sum(CASE WHEN j.food_satisfaction_score <= $max_score THEN 1 ELSE 0 END) as bad 
            RETURN fleet, (toFloat(bad)/total)*100 as Failure_Rate
        """,

        # =========================================================
        # 2. OPERATIONAL PERFORMANCE & DELAYS
        # =========================================================

        "analytics.ops.avg_delay_fleet": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, avg(j.arrival_delay_minutes) as avg_delay
        """,

        "analytics.ops.origin_delay": """
            MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport) 
            RETURN a.station_code, avg(j.arrival_delay_minutes) as delay 
            ORDER BY delay DESC LIMIT 1
        """,

        "analytics.ops.dest_delay": """
            MATCH (j:Journey)-[:ON]->(f:Flight)-[:ARRIVES_AT]->(a:Airport) 
            RETURN a.station_code, avg(j.arrival_delay_minutes) as delay 
            ORDER BY delay DESC LIMIT 1
        """,

        "analytics.ops.correlation_miles_delay": """
            MATCH (j:Journey) 
            RETURN j.actual_flown_miles, j.arrival_delay_minutes
        """,

        "analytics.ops.chronic_delay_flights": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WITH f.flight_number as num, count(j) as total, 
                 sum(CASE WHEN j.arrival_delay_minutes > 0 THEN 1 ELSE 0 END) as delayed 
            WHERE (toFloat(delayed)/total) > 0.5 
            RETURN num
        """,

        "analytics.ops.delay_by_class": """
            MATCH (j:Journey) 
            RETURN j.passenger_class, avg(j.arrival_delay_minutes) as avg_delay
        """,

        "analytics.ops.total_delay_fleet": """
            MATCH (j:Journey)-[:ON]->(f:Flight {fleet_type_description: $fleet_type}) 
            RETURN sum(j.arrival_delay_minutes) as total_delay_minutes
        """,

        "analytics.ops.best_route_otp": """
            MATCH (o)<-[:DEPARTS_FROM]-(f)-[:ARRIVES_AT]->(d), (j)-[:ON]->(f) 
            RETURN o.station_code, d.station_code, avg(j.arrival_delay_minutes) as avg_delay 
            ORDER BY avg_delay ASC LIMIT 1
        """,

        "analytics.ops.worst_route_otp": """
            MATCH (o)<-[:DEPARTS_FROM]-(f)-[:ARRIVES_AT]->(d), (j)-[:ON]->(f) 
            RETURN o.station_code, d.station_code, avg(j.arrival_delay_minutes) as avg_delay 
            ORDER BY avg_delay DESC LIMIT 1
        """,

        "analytics.ops.legs_vs_delay": """
            MATCH (j:Journey) 
            RETURN j.number_of_legs, avg(j.arrival_delay_minutes) as avg_delay
        """,

        "analytics.ops.long_haul_delay": """
            MATCH (j:Journey) 
            WHERE j.actual_flown_miles > $min_miles 
            RETURN avg(j.arrival_delay_minutes) as avg_delay
        """,

        "analytics.ops.short_haul_reliability": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WHERE j.actual_flown_miles < $max_miles 
            RETURN f.fleet_type_description, avg(j.arrival_delay_minutes) as delay 
            ORDER BY delay ASC LIMIT 1
        """,

        "analytics.ops.perfect_flights": """
            MATCH (f:Flight)<-[:ON]-(j:Journey) 
            WHERE j.arrival_delay_minutes = 0 
            RETURN distinct f.flight_number
        """,

        "analytics.ops.global_delay_pct": """
            MATCH (j:Journey) 
            WITH count(j) as total, sum(CASE WHEN j.arrival_delay_minutes > $min_delay THEN 1 ELSE 0 END) as delayed 
            RETURN (toFloat(delayed)/total)*100 as Percentage
        """,

        "analytics.ops.generation_delay_dist": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            RETURN p.generation, avg(j.arrival_delay_minutes) as avg_delay
        """,

        "analytics.ops.route_variance": """
            MATCH (o)<-[:DEPARTS_FROM]-(f)-[:ARRIVES_AT]->(d), (j)-[:ON]->(f) 
            RETURN o.station_code, d.station_code, stDev(j.arrival_delay_minutes) as variance 
            ORDER BY variance DESC
        """,

        "analytics.ops.audit_loyalty_service": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            RETURN p.loyalty_program_level, avg(j.arrival_delay_minutes) as avg_delay
        """,

        "analytics.ops.max_delay": """
            MATCH (j:Journey) 
            RETURN max(j.arrival_delay_minutes) as max_delay
        """,

        "analytics.ops.long_delay_origin": """
            MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport) 
            WHERE j.arrival_delay_minutes > $min_delay 
            RETURN a.station_code, count(*) as long_delays 
            ORDER BY long_delays DESC LIMIT 1
        """,

        "analytics.ops.early_arrival_miles": """
            MATCH (j:Journey) 
            WHERE j.arrival_delay_minutes < 0 
            RETURN avg(j.actual_flown_miles) as avg_miles
        """,

        # =========================================================
        # 3. LOYALTY & CUSTOMER SEGMENTATION
        # =========================================================

        "analytics.loyalty.breakdown": """
            MATCH (p:Passenger) 
            RETURN p.loyalty_program_level, count(*) as count
        """,

        "analytics.loyalty.platinum_generation": """
            MATCH (p:Passenger {loyalty_program_level: $loyalty_level}) 
            RETURN p.generation, count(*) as count 
            ORDER BY count DESC LIMIT 1
        """,

        "analytics.loyalty.class_preference": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            RETURN p.loyalty_program_level, j.passenger_class, count(*) as count 
            ORDER BY count DESC
        """,

        "analytics.loyalty.generation_miles": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            RETURN p.generation, avg(j.actual_flown_miles) as avg_miles 
            ORDER BY avg_miles DESC
        """,

        "analytics.loyalty.fleet_preference": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight) 
            RETURN p.loyalty_program_level, f.fleet_type_description, count(*) as frequency
        """,

        "analytics.loyalty.retention_rate": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WITH p, count(j) as trips 
            WHERE trips > 1 
            RETURN count(p) as Returning_Passengers
        """,

        "analytics.loyalty.feedback_volume": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            RETURN p.loyalty_program_level, count(j.feedback_ID) as count 
            ORDER BY count DESC
        """,

        "analytics.loyalty.entry_level_satisfaction": """
            MATCH (p:Passenger {loyalty_program_level: $loyalty_level})-[:TOOK]->(j:Journey) 
            RETURN avg(j.food_satisfaction_score) as avg_score
        """,

        "analytics.loyalty.top_tier_routes": """
            MATCH (p:Passenger {loyalty_program_level: $loyalty_level})-[:TOOK]->(j:Journey)-[:ON]->(f:Flight), (f)-[:DEPARTS_FROM]->(o), (f)-[:ARRIVES_AT]->(d) 
            RETURN o.station_code, d.station_code, count(*) as popularity 
            ORDER BY popularity DESC
        """,

        "analytics.loyalty.genx_class_ratio": """
            MATCH (p:Passenger {generation: $generation})-[:TOOK]->(j:Journey) 
            RETURN j.passenger_class, count(*) as count
        """,

        "analytics.loyalty.high_mileage_users": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WITH p, sum(j.actual_flown_miles) as total_miles 
            WHERE total_miles > $min_miles 
            RETURN p.record_locator
        """,

        "analytics.loyalty.multileg_generation": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WHERE j.number_of_legs > 1 
            RETURN p.generation, count(*) as count 
            ORDER BY count DESC
        """,

        "analytics.loyalty.passenger_count": """
            MATCH (p:Passenger) 
            RETURN count(distinct p) as total_passengers
        """,

        "analytics.loyalty.top_tier_delays": """
            MATCH (p:Passenger {loyalty_program_level: $loyalty_level})-[:TOOK]->(j:Journey) 
            RETURN avg(j.arrival_delay_minutes) as avg_delay
        """,

        "analytics.loyalty.high_value_origin": """
            MATCH (p:Passenger {loyalty_program_level: $loyalty_level})-[:TOOK]->(j:Journey)-[:ON]->(f)-[:DEPARTS_FROM]->(a:Airport) 
            RETURN a.station_code, count(distinct p) as pax_count 
            ORDER BY pax_count DESC
        """,

        "analytics.loyalty.gen_comparison": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WHERE p.generation IN $generations 
            RETURN p.generation, j.passenger_class, count(*) as count
        """,

        "analytics.loyalty.tolerance": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WHERE j.arrival_delay_minutes > $min_delay 
            RETURN p.loyalty_program_level, avg(j.food_satisfaction_score) as score 
            ORDER BY score DESC
        """,

        "analytics.loyalty.tier_mileage": """
            MATCH (p:Passenger {loyalty_program_level: $loyalty_level})-[:TOOK]->(j:Journey) 
            RETURN sum(j.actual_flown_miles) as total_miles
        """,

        "analytics.loyalty.no_level_count": """
            MATCH (p:Passenger) 
            WHERE p.loyalty_program_level IS NULL 
            RETURN count(p) as count
        """,

        "analytics.loyalty.gold_fleet": """
            MATCH (p:Passenger {loyalty_program_level: $loyalty_level})-[:TOOK]->(j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, count(*) as count 
            ORDER BY count DESC LIMIT 1
        """,

        # =========================================================
        # 4. FLEET & NETWORK ANALYSIS
        # =========================================================

        "analytics.network.fleet_count": """
            MATCH (f:Flight) 
            RETURN count(distinct f.fleet_type_description) as unique_fleets
        """,

        "analytics.network.fleet_range": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, avg(j.actual_flown_miles) as dist 
            ORDER BY dist DESC
        """,

        "analytics.network.fleet_legs": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, avg(j.number_of_legs) as avg_legs 
            ORDER BY avg_legs DESC
        """,

        "analytics.network.airport_aircraft": """
            MATCH (f:Flight)-[:ARRIVES_AT]->(a:Airport {station_code: $station_code}) 
            RETURN f.fleet_type_description, count(*) as count 
            ORDER BY count DESC LIMIT 1
        """,

        "analytics.network.fleet_capacity": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, count(distinct p) / count(distinct f.flight_number) as approx_capacity 
            ORDER BY approx_capacity DESC
        """,

        "analytics.network.hub_identification": """
            MATCH (a:Airport)<-[:ARRIVES_AT|DEPARTS_FROM]-(f:Flight) 
            RETURN a.station_code, count(f) as degree 
            ORDER BY degree DESC
        """,

        "analytics.network.fleet_restrictions": """
            MATCH (f:Flight)-[:ARRIVES_AT]->(a:Airport) 
            WITH collect(distinct f.fleet_type_description) as visited_fleets, a 
            MATCH (all_fleets:Flight) 
            WITH collect(distinct all_fleets.fleet_type_description) as global_fleets, visited_fleets, a 
            RETURN a.station_code, [x IN global_fleets WHERE NOT x IN visited_fleets] as never_visits
        """,

        "analytics.network.fleet_utilization": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, sum(j.actual_flown_miles) as total_miles
        """,

        "analytics.network.biz_class_fleet": """
            MATCH (j:Journey {passenger_class: $passenger_class})-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, count(*) as count 
            ORDER BY count DESC
        """,

        "analytics.network.airport_count": """
            MATCH (a:Airport) 
            RETURN count(a) as total_airports
        """,

        "analytics.network.fleet_cx_fail": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, avg(j.food_satisfaction_score) as score 
            ORDER BY score ASC LIMIT 1
        """,

        "analytics.network.orphan_airports": """
            MATCH (a:Airport)<-[:ARRIVES_AT|DEPARTS_FROM]-(f:Flight) 
            WITH a, count(distinct f) as flights 
            WHERE flights <= 2 
            RETURN a.station_code
        """,

        "analytics.network.demographic_utilization": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight) 
            RETURN p.generation, f.fleet_type_description, count(*) as count
        """,

        "analytics.network.multileg_aircraft": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WHERE j.number_of_legs > 1 
            RETURN f.fleet_type_description, count(*) as count 
            ORDER BY count DESC
        """,

        "analytics.network.economy_workhorse": """
            MATCH (j:Journey {passenger_class: 'Economy'})-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, count(*) as count 
            ORDER BY count DESC LIMIT 1
        """,

        "analytics.network.shorthaul_only": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WITH f.fleet_type_description as fleet, max(j.actual_flown_miles) as max_dist 
            WHERE max_dist < $max_miles 
            RETURN fleet
        """,

        "analytics.network.load_factor": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.flight_number, count(j) as passengers
        """,

        "analytics.network.delay_prone_fleets": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WHERE j.arrival_delay_minutes > $min_delay 
            RETURN f.fleet_type_description, count(*) as count 
            ORDER BY count DESC
        """,

        "analytics.network.route_frequency": """
            MATCH (f:Flight)-[:DEPARTS_FROM]->(o:Airport {station_code: $origin}), (f)-[:ARRIVES_AT]->(d:Airport {station_code: $dest}) 
            RETURN count(f) as flight_count
        """,

        "analytics.network.consistent_cx": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            RETURN f.fleet_type_description, stDev(j.food_satisfaction_score) as variability 
            ORDER BY variability ASC LIMIT 1
        """,

        # =========================================================
        # 5. GRAPH-SPECIFIC & ADVANCED ANALYTICS
        # =========================================================

        "graph.path.specific_criteria": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight), 
                  (f)-[:DEPARTS_FROM]->(:Airport {station_code: $origin}), 
                  (f)-[:ARRIVES_AT]->(:Airport {station_code: $dest}) 
            WHERE f.fleet_type_description = $fleet_type 
            RETURN p.record_locator
        """,

        "graph.path.sequence": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(o:Airport), 
                  (f)-[:ARRIVES_AT]->(d:Airport) 
            RETURN p.record_locator, collect(o.station_code + '->' + d.station_code) as path 
            ORDER BY j.feedback_ID
        """,

        "graph.collab.co_passengers": """
            MATCH (vip:Passenger {record_locator: $vip_id})-[:TOOK]->(:Journey)-[:ON]->(f:Flight)<-[:ON]-(:Journey)<-[:TOOK]-(copassenger:Passenger) 
            RETURN distinct copassenger.record_locator
        """,

        "graph.pattern.complete_coverage": """
            MATCH (f:Flight) 
            WITH collect(distinct f.fleet_type_description) as all_fleets 
            MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f_flown:Flight) 
            WITH p, all_fleets, collect(distinct f_flown.fleet_type_description) as flown_fleets 
            WHERE size(flown_fleets) = size(all_fleets) 
            RETURN p.record_locator
        """,

        "graph.analytics.super_connector": """
            MATCH (a:Airport)<-[:DEPARTS_FROM]-(f:Flight)<-[:ON]-(j:Journey) 
            WHERE j.arrival_delay_minutes > $min_delay AND j.food_satisfaction_score < $max_score 
            RETURN a.station_code, count(distinct f) as incidents 
            ORDER BY incidents DESC
        """,

        "graph.analytics.route_clustering": """
            MATCH (f:Flight)-[:DEPARTS_FROM]->(o), (f)-[:ARRIVES_AT]->(d) 
            WITH o.station_code + '-' + d.station_code as route, count(distinct f) as freq 
            RETURN route, freq 
            ORDER BY freq DESC
        """,

        "graph.flow.feeder_airports": """
            MATCH (j:Journey)-[:ON]->(f:Flight)-[:DEPARTS_FROM]->(a:Airport) 
            WHERE j.actual_flown_miles > $min_miles 
            RETURN a.station_code, count(distinct p) as passengers_fed 
            ORDER BY passengers_fed DESC
        """,

        "graph.algo.degree_centrality": """
            MATCH (a:Airport) 
            RETURN a.station_code, size((a)--()) as degree 
            ORDER BY degree DESC
        """,

        "graph.pattern.consecutive_delays": """
            MATCH (p:Passenger)-[:TOOK]->(j1:Journey), (p)-[:TOOK]->(j2:Journey) 
            WHERE j1.arrival_delay_minutes > $min_delay AND j2.arrival_delay_minutes > $min_delay AND j1 <> j2 
            RETURN distinct p.record_locator
        """,

        "graph.analytics.bridge_flights": """
            MATCH (c1:Airport {station_code: $cluster_a}), (c2:Airport {station_code: $cluster_b}), (f:Flight) 
            WHERE (f)-[:DEPARTS_FROM]->(c1) AND (f)-[:ARRIVES_AT]->(c2) 
            RETURN f.flight_number
        """,

        "graph.path.constrained_routing": """
            MATCH path = (a:Airport {station_code: $origin})<-[:DEPARTS_FROM]-(f:Flight)-[:ARRIVES_AT]->(b:Airport {station_code: $dest}) 
            WHERE f.fleet_type_description = $fleet_type 
            RETURN path
        """,

        "graph.analytics.explorer_passengers": """
            MATCH (p:Passenger)-[:TOOK]->(:Journey)-[:ON]->(:Flight)-[:ARRIVES_AT]->(d:Airport) 
            RETURN p.record_locator, count(distinct d) as unique_dests 
            ORDER BY unique_dests DESC
        """,

        "graph.algo.shortest_path": """
            MATCH (start:Airport {station_code: $origin}), (end:Airport {station_code: $dest}) 
            MATCH path = shortestPath((start)-[*]-(end)) 
            RETURN path
        """,

        "graph.similarity.satisfaction_profile": """
            MATCH (p1:Passenger)-[:TOOK]->(j1:Journey), (p2:Passenger)-[:TOOK]->(j2:Journey) 
            WHERE p1 <> p2 AND j1.food_satisfaction_score = j2.food_satisfaction_score AND j1.passenger_class = j2.passenger_class 
            RETURN p1.record_locator, p2.record_locator LIMIT 10
        """,

        "graph.anomaly.catering_fail": """
            MATCH (j:Journey)-[:ON]->(f:Flight) 
            WITH f, collect(j.food_satisfaction_score) as scores 
            WHERE all(s IN scores WHERE s <= 2) 
            RETURN f.flight_number
        """,

        "graph.flow.next_best_action": """
            MATCH (p:Passenger)-[:TOOK]->(j1:Journey)-[:ON]->(:Flight)-[:ARRIVES_AT]->(mid:Airport {station_code: $station_code}) 
            MATCH (p)-[:TOOK]->(j2:Journey)-[:ON]->(:Flight)-[:DEPARTS_FROM]->(mid)-[:ARRIVES_AT]->(next:Airport) 
            RETURN next.station_code, count(*) as freq 
            ORDER BY freq DESC
        """,

        "graph.analytics.aircraft_loyalty": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight {fleet_type_description: $fleet_type}) 
            RETURN p.record_locator, sum(j.actual_flown_miles) as total 
            ORDER BY total DESC
        """,

        "graph.cx.hub_transfer_effect": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WHERE j.number_of_legs > 1 
            RETURN avg(j.food_satisfaction_score) as avg_score
        """,

        "graph.pattern.circular_journey": """
            MATCH (p:Passenger)-[:TOOK]->(j_out)-[:ON]->(f_out)-[:DEPARTS_FROM]->(start:Airport), 
                  (p)-[:TOOK]->(j_in)-[:ON]->(f_in)-[:ARRIVES_AT]->(start) 
            WHERE j_out.feedback_ID < j_in.feedback_ID 
            RETURN p.record_locator
        """,

        "graph.segmentation.unhappy_influencers": """
            MATCH (p:Passenger)-[:TOOK]->(j:Journey) 
            WHERE p.loyalty_program_level IN $loyalty_levels 
              AND j.arrival_delay_minutes > $min_delay AND j.food_satisfaction_score < $max_score 
            RETURN p.record_locator
        """
    }

    def __init__(self, driver=None):
        """
        Initialize the retriever with a Neo4j driver.
        If no driver is provided, it attempts to use the default one from config.
        """
        self.driver = driver if driver else default_driver

    def run_query(self, intent, entities):
        """
        Selects the correct template and executes it against Neo4j.
        """
        if intent not in self.CYPHER_TEMPLATES:
            return f"Error: No template found for intent '{intent}'"
        
        query = self.CYPHER_TEMPLATES[intent]
        
        # Connect to Neo4j
        try:
            if self.driver is None:
                return "Database Error: Driver not initialized."

            records, summary, keys = self.driver.execute_query(
                query,
                entities, # Pass the dictionary directly as parameters
                database_="neo4j", 
            )
            
            # Format results nicely for the LLM Context
            results = [dict(record) for record in records]
            return results

        except Exception as e:
            return f"Database Error: {e}"

    def get_available_intents(self):
        """
        Returns a list of all available intent keys from CYPHER_TEMPLATES.
        """
        return list(self.CYPHER_TEMPLATES.keys())

# --- Main Pipeline Integration ---
if __name__ == "__main__":
    # Simulate data coming from preprocess.py
    # Example: User asked "Find severe delays > 60 mins with rating < 2"
    processed_input = {
        "intent": "find_severe_service_issues", # Note: This intent key doesn't actually exist in the map above, but keeping the example structure
        "entities": {"min_delay": 60, "max_score": 2}
    }
    
    # Use a valid intent for the test if possible, or handle the error
    test_intent = "analytics.ops.long_delay_origin"
    test_entities = {"min_delay": 120}

    print(f"Initializing Neo4jRetriever...")
    retriever = Neo4jRetriever()
    
    print(f"Executing Intent: {test_intent}...")
    graph_data = retriever.run_query(test_intent, test_entities)
    
    print("--- Graph Results ---")
    print(graph_data)