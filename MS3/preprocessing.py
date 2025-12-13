#!/usr/bin/env python3
import os
import sys
import json
import re
import spacy
from spacy.pipeline import EntityRuler

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.openai_client import get_answer
from config.neo4j_client import driver as default_driver # Adjusted import to match your structure
from MS3.base_retrieve import Neo4jRetriever

# ==========================================
# SEMANTIC REFERENCE VALUES
# Used by LLM to infer numeric thresholds from qualitative terms
# ==========================================
SEMANTIC_THRESHOLDS = {
    "delay": {
        "early": {"max_delay": 0},
        "on_time": {"min_delay": -15, "max_delay": 15},
        "slight": {"min_delay": 1, "max_delay": 15},
        "moderate": {"min_delay": 16, "max_delay": 60},
        "severe": {"min_delay": 61},
        "extreme": {"min_delay": 120}
    },
    "food_satisfaction": {
        "poor": {"max_food_satisfaction": 2},
        "bad": {"max_food_satisfaction": 2},
        "low": {"max_food_satisfaction": 2},
        "mid": {"min_food_satisfaction": 3, "max_food_satisfaction": 3},
        "good": {"min_food_satisfaction": 4},
        "excellent": {"min_food_satisfaction": 5},
        "high": {"min_food_satisfaction": 4}
    },
    "distance": {
        "short": {"max_miles": 1000},
        "short-haul": {"max_miles": 1000},
        "medium": {"min_miles": 1000, "max_miles": 4000},
        "medium-haul": {"min_miles": 1000, "max_miles": 4000},
        "long": {"min_miles": 4000},
        "long-haul": {"min_miles": 4000}
    },
    "legs": {
        "direct": {"max_legs": 1},
        "nonstop": {"max_legs": 1},
        "single": {"max_legs": 1},
        "connecting": {"min_legs": 2},
        "multi-leg": {"min_legs": 2},
        "multi": {"min_legs": 2},
        "complex": {"min_legs": 3}
    }
}


class QueryPreprocessor:
    """
    Handles preprocessing using Hybrid NER (spaCy + Rules) instead of pure LLMs for extraction.
    """
    
    def __init__(self, retriever):
        self.retriever = retriever
        
        # --- 1. Load spaCy Model ---
        print("Loading NER models...")
        self.nlp = spacy.load("en_core_web_sm")
        
        # --- 2. Add Custom Entity Ruler ---
        # This allows us to define specific airline patterns that the base model doesn't know.
        # We add it *before* the 'ner' component so our rules take precedence.
        if "entity_ruler" not in self.nlp.pipe_names:
            ruler = self.nlp.add_pipe("entity_ruler", before="ner")
            
            patterns = [
                # -- Loyalty Tiers --
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "premier"}, {"LOWER": "gold"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "premier"}, {"LOWER": "silver"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "premier"}, {"LOWER": "platinum"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "premier"}, {"LOWER": "1k"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "non-elite"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "non"}, {"LOWER": "-"}, {"LOWER": "elite"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "non"}, {"LOWER": "elite"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "nonelite"}]},
                {"label": "LOYALTY_TIER", "pattern": [{"TEXT": {"REGEX": "^[Nn]on-?[Ee]lite$"}}]},

                # -- Generations --
                {"label": "GENERATION", "pattern": [{"LOWER": "boomer"}]},
                {"label": "GENERATION", "pattern": [{"LOWER": "boomers"}]}, # Plural handling
                {"label": "GENERATION", "pattern": [{"LOWER": "millennial"}]},
                {"label": "GENERATION", "pattern": [{"LOWER": "millennials"}]},
                {"label": "GENERATION", "pattern": [{"LOWER": "gen"}, {"LOWER": "x"}]},
                {"label": "GENERATION", "pattern": [{"LOWER": "gen"}, {"LOWER": "z"}]},

                # -- Cabin Class --
                {"label": "CLASS", "pattern": [{"LOWER": "economy"}]},
                {"label": "CLASS", "pattern": [{"LOWER": "business"}]},
                {"label": "CLASS", "pattern": [{"LOWER": "first"}, {"LOWER": "class"}]},

                # -- Fleet/Aircraft --
                # Matches patterns like "B777", "A320", "Boeing 777"
                {"label": "FLEET", "pattern": [
                    {"TEXT": {"REGEX": "^[BA][0-9]{3}$"}}, 
                    {"TEXT": "-"}, 
                    {"TEXT": {"REGEX": "^[0-9]+$"}}
                ]},
                {"label": "FLEET", "pattern": [{"TEXT": {"REGEX": "^[BA][0-9]{3}(-[0-9]+)?$"}}]}, 
                {"label": "FLEET", "pattern": [{"LOWER": "boeing"}, {"TEXT": {"REGEX": "^7[0-9]{2}$"}}]},
                {"label": "FLEET", "pattern": [{"LOWER": "airbus"}, {"TEXT": {"REGEX": "^3[0-9]{2}$"}}]},

                # -- Airport Codes (Simple 3-Letter Uppercase) --
                # Note: This is aggressive regex. In production, validate against a DB list.
                {"label": "AIRPORT", "pattern": [{"TEXT": {"REGEX": "^[A-Z]{3}$"}}]},
                
                # -- Record Locators (6 char alphanumeric) --
                {"label": "LOCATOR", "pattern": [{"TEXT": {"REGEX": "^[A-Z0-9]{6}$"}}]}
            ]
            ruler.add_patterns(patterns)


    def classify_intent(self, user_input):
        """
        Uses LLM to classify intent. (Kept as is, since Intent classification is hard for Regex)
        """
        available_intents = self.retriever.get_available_intents()
        
        prompt = f"""
        You are an intent classifier for an airline system.
        User Input: "{user_input}"
        Available Intents: {json.dumps(available_intents)}
        
        Intent descriptions:
        - analyze_delays: Questions about flight delays, delay statistics, punctuality
        - analyze_satisfaction: Questions about food satisfaction scores, service ratings
        - search_network: Searching for flights, routes between airports, flights by mileage/distance
        - analyze_issues: Finding problematic flights with delays AND poor ratings combined
        - lookup_details: Looking up specific passenger record or feedback by ID
        - analyze_passengers: Questions about passenger demographics, passenger statistics by generation
        - analyze_journeys: Questions about journey characteristics like legs, mileage, class statistics
        - compare_routes: Comparing performance metrics across different routes
        - analyze_loyalty: Questions about loyalty program levels, most common loyalty tier, loyalty distribution
        - analyze_experience: Questions about average experience, aggregate statistics for a group (e.g., "average experience for premier gold members")
        
        Return ONLY the intent key. Default to "unknown".
        """
        intent = get_answer(prompt).strip().replace('"', '').replace("'", "")
        return intent if intent in available_intents else "unknown"


    def extract_parameters_with_llm(self, user_input, intent):
        """
        Uses LLM to infer numeric parameters from semantic/qualitative terms.
        This handles terms like 'severe delays', 'poor ratings', 'long-haul flights'.
        """
        prompt = f"""
        You are a parameter extractor for an airline query system.
        
        User Input: "{user_input}"
        Intent: {intent}
        
        REFERENCE VALUES for semantic inference:
        
        DELAY THRESHOLDS (in minutes - ALWAYS convert hours to minutes: 1 hour = 60 minutes):
        - "early" or "ahead of schedule": max_delay = 0
        - "on time" or "punctual": min_delay = -15, max_delay = 15  
        - "slight delay": min_delay = 1, max_delay = 15
        - "moderate delay": min_delay = 16, max_delay = 60
        - "severe delay" or "significant delay": min_delay = 61
        - "extreme delay" or "major delay": min_delay = 120
        - "1 hour" or "an hour": min_delay = 60
        - "2 hours": min_delay = 120
        - "more than X hours": min_delay = X * 60
        
        FOOD SATISFACTION THRESHOLDS (scores 1-5):
        - "poor", "bad", "low", "terrible": max_food_satisfaction = 2
        - "average", "okay", "mediocre": min_food_satisfaction = 3, max_food_satisfaction = 3
        - "good", "high", "great": min_food_satisfaction = 4
        - "excellent", "outstanding": min_food_satisfaction = 5
        
        DISTANCE THRESHOLDS (in miles):
        - "short" or "short-haul": max_miles = 1000
        - "medium" or "medium-haul": min_miles = 1000, max_miles = 4000
        - "long" or "long-haul": min_miles = 4000
        
        LEG THRESHOLDS:
        - "direct", "nonstop", "single": max_legs = 1
        - "connecting", "multi-leg": min_legs = 2
        - "complex": min_legs = 3
        
        Extract ONLY numeric parameters. If the user provides explicit numbers, use those.
        If the user uses qualitative terms (like "severe", "poor", "long"), infer the appropriate thresholds.
        
        Return a JSON object with ONLY these possible keys (include only those that apply):
        - min_delay: integer (minimum delay in minutes)
        - max_delay: integer (maximum delay in minutes)
        - min_food_satisfaction: integer 1-5 (minimum food score)
        - max_food_satisfaction: integer 1-5 (maximum food score)
        - min_miles: integer (minimum miles)
        - max_miles: integer (maximum miles)
        - min_legs: integer (minimum number of legs)
        - max_legs: integer (maximum number of legs)
        - max_score: integer 1-5 (legacy alias for max_food_satisfaction)
        
        Return ONLY the JSON object, no explanation. If no parameters apply, return {{}}.
        """
        
        try:
            response = get_answer(prompt).strip()
            # Clean up response - remove markdown code blocks if present
            response = response.replace('```json', '').replace('```', '').strip()
            parameters = json.loads(response)
            return parameters
        except (json.JSONDecodeError, Exception) as e:
            print(f"Parameter extraction error: {e}")
            return {}


    def extract_entities(self, user_input, intent):
        """
        REPLACED LLM with spaCy NER Pipeline.
        Extracts ENTITIES only (flights, airports, passengers, journeys, routes).
        Numeric parameters are handled separately by extract_parameters_with_llm().
        """
        doc = self.nlp(user_input)
        entities = {}

        # --- 1. Basic Entity Extraction from Ruler ---
        for ent in doc.ents:
            # Clean up the text (e.g., "Boomers" -> "Boomer")
            val = ent.text
            
            if ent.label_ == "GENERATION":
                # Basic normalization
                if "boomer" in val.lower(): val = "Boomer"
                elif "millennial" in val.lower(): val = "Millennial"
                elif "gen x" in val.lower(): val = "Gen X"
                elif "gen z" in val.lower(): val = "Gen Z"
                entities["generation"] = val
            
            elif ent.label_ == "LOYALTY_TIER":
                # Normalize loyalty tier
                tier_lower = val.lower()
                if 'gold' in tier_lower: val = "premier gold"
                elif 'silver' in tier_lower: val = "premier silver"
                elif 'platinum' in tier_lower: val = "premier platinum"
                elif '1k' in tier_lower: val = "premier 1k"
                elif 'non' in tier_lower or 'elite' in tier_lower: val = "non-elite"
                entities["loyalty_tier"] = val
            
            elif ent.label_ == "CLASS":
                entities["class"] = val.title() # e.g., "Economy"
            
            elif ent.label_ == "FLEET":
                entities["fleet_type"] = val.upper()
            
            elif ent.label_ == "LOCATOR":
                entities["record_locator"] = val
            
            elif ent.label_ == "FEEDBACK_ID":
                entities["feedback_id"] = val
            
            elif ent.label_ == "AIRPORT":
                # Logic to distinguish Origin vs Dest based on prepositions
                # Look at the word immediately 'before' the airport code
                token_index = ent.start
                if token_index > 0:
                    prev_word = doc[token_index - 1].text.lower()
                    if prev_word in ["from", "departing", "out", "leaving"]:
                        entities["origin"] = val
                    elif prev_word in ["to", "arriving", "into", "towards"]:
                        entities["dest"] = val
                    else:
                        # Fallback: If we have an origin, this must be dest, else origin
                        if "origin" not in entities:
                            entities["origin"] = val
                        else:
                            entities["dest"] = val
                else:
                    # First word is airport? Assume origin usually
                    entities["origin"] = val

        # --- 2. Feedback ID extraction (pattern: F_XX) ---
        feedback_match = re.search(r'\b(F_\d+)\b', user_input, re.IGNORECASE)
        if feedback_match:
            entities["feedback_id"] = feedback_match.group(1).upper()

        return entities


    def extract_parameters_from_text(self, user_input):
        """
        Extracts explicit numeric parameters from text using regex.
        This catches cases where users provide exact numbers.
        """
        parameters = {}
        
        # Explicit mileage patterns - MUST have "miles" to avoid matching "minutes"
        miles_greater = re.search(r'(?:longer|greater|more|over|above|exceeding|at least|minimum)\s*(?:than\s*)?(\d+)\s*miles?', user_input, re.IGNORECASE)
        miles_less = re.search(r'(?:shorter|less|under|below|within|at most|maximum)\s*(?:than\s*)?(\d+)\s*miles?', user_input, re.IGNORECASE)
        miles_exact = re.search(r'(\d{3,5})\s*miles?', user_input, re.IGNORECASE)
        
        if miles_greater:
            parameters["min_miles"] = int(miles_greater.group(1))
        if miles_less:
            parameters["max_miles"] = int(miles_less.group(1))
        elif miles_exact and 'min_miles' not in parameters:
            # If just a number mentioned with miles, assume minimum
            parameters["min_miles"] = int(miles_exact.group(1))
        
        # Explicit delay patterns
        delay_greater = re.search(r'(?:delay|delayed|late).*?(?:over|above|more than|greater than|exceeding|at least)\s*(\d+)', user_input, re.IGNORECASE)
        delay_less = re.search(r'(?:delay|delayed|late).*?(?:under|below|less than|within|at most)\s*(\d+)', user_input, re.IGNORECASE)
        delay_greater_alt = re.search(r'(?:over|above|more than|greater than|exceeding|at least)\s*(\d+)\s*(?:min|minute)', user_input, re.IGNORECASE)
        delay_range = re.search(r'(\d+)\s*(?:to|-)\s*(\d+)\s*(?:min|minute)', user_input, re.IGNORECASE)
        
        # Hour conversion patterns
        hour_pattern = re.search(r'(?:more than|over|above|at least|exceeding)\s*(\d+)\s*hours?', user_input, re.IGNORECASE)
        hour_pattern_alt = re.search(r'(\d+)\s*hours?\s*(?:delay|late|delayed)', user_input, re.IGNORECASE)
        # Handle "an hour" or "a hour" as 1 hour
        an_hour_pattern = re.search(r'(?:more than|over|above|at least|exceeding)?\s*(?:an?|one)\s*hours?', user_input, re.IGNORECASE)
        
        if an_hour_pattern:
            parameters["min_delay"] = 60
        elif hour_pattern:
            parameters["min_delay"] = int(hour_pattern.group(1)) * 60
        elif hour_pattern_alt:
            parameters["min_delay"] = int(hour_pattern_alt.group(1)) * 60
        elif delay_range:
            parameters["min_delay"] = int(delay_range.group(1))
            parameters["max_delay"] = int(delay_range.group(2))
        elif delay_greater:
            parameters["min_delay"] = int(delay_greater.group(1))
        elif delay_greater_alt:
            parameters["min_delay"] = int(delay_greater_alt.group(1))
        elif delay_less:
            parameters["max_delay"] = int(delay_less.group(1))
        
        # Explicit satisfaction/rating patterns
        score_less = re.search(r'(?:rating|score|satisfaction).*?(?:under|below|less than|at most|poor|bad)\s*(\d)', user_input, re.IGNORECASE)
        score_greater = re.search(r'(?:rating|score|satisfaction).*?(?:over|above|more than|at least|good|excellent)\s*(\d)', user_input, re.IGNORECASE)
        
        if score_less:
            parameters["max_food_satisfaction"] = int(score_less.group(1))
        if score_greater:
            parameters["min_food_satisfaction"] = int(score_greater.group(1))
        
        # Explicit leg patterns
        legs_greater = re.search(r'(?:more than|at least|over|above|exceeding|minimum)\s*(\d+)\s*(?:leg|stop|connection)', user_input, re.IGNORECASE)
        legs_less = re.search(r'(?:less than|at most|under|below|within|maximum)\s*(\d+)\s*(?:leg|stop|connection)', user_input, re.IGNORECASE)
        legs_exact = re.search(r'(\d+)\s*(?:leg|stop|connection)', user_input, re.IGNORECASE)
        
        if legs_greater:
            parameters["min_legs"] = int(legs_greater.group(1))
        if legs_less:
            parameters["max_legs"] = int(legs_less.group(1))
        elif legs_exact and 'min_legs' not in parameters and 'max_legs' not in parameters:
            # Exact number of legs
            parameters["min_legs"] = int(legs_exact.group(1))
            parameters["max_legs"] = int(legs_exact.group(1))
        
        return parameters


    def infer_semantic_parameters(self, user_input):
        """
        Infers parameters from semantic/qualitative terms without LLM.
        Used as a fallback or complement to LLM-based extraction.
        """
        parameters = {}
        input_lower = user_input.lower()
        
        # Delay inference - check for various patterns including typos
        if any(word in input_lower for word in ['severe', 'severely', 'severly', 'major delay', 'significant', 'big delay', 'huge delay']):
            parameters["min_delay"] = SEMANTIC_THRESHOLDS["delay"]["severe"]["min_delay"]
        elif any(word in input_lower for word in ['extreme', 'very delayed', 'massive', 'extremely']):
            parameters["min_delay"] = SEMANTIC_THRESHOLDS["delay"]["extreme"]["min_delay"]
        elif any(word in input_lower for word in ['moderate', 'moderately']):
            parameters.update(SEMANTIC_THRESHOLDS["delay"]["moderate"])
        elif any(word in input_lower for word in ['slight', 'minor', 'small delay', 'little delay']):
            parameters.update(SEMANTIC_THRESHOLDS["delay"]["slight"])
        elif any(word in input_lower for word in ['on time', 'punctual', 'no delay']):
            parameters.update(SEMANTIC_THRESHOLDS["delay"]["on_time"])
        elif 'early' in input_lower and 'delay' not in input_lower:
            parameters["max_delay"] = 0
        
        # Food satisfaction inference
        if any(word in input_lower for word in ['poor rating', 'poor food', 'bad rating', 'bad food', 'low satisfaction', 'terrible']):
            parameters["max_food_satisfaction"] = SEMANTIC_THRESHOLDS["food_satisfaction"]["poor"]["max_food_satisfaction"]
        elif any(word in input_lower for word in ['excellent rating', 'excellent food', 'great food', 'high satisfaction']):
            parameters["min_food_satisfaction"] = SEMANTIC_THRESHOLDS["food_satisfaction"]["excellent"]["min_food_satisfaction"]
        elif any(word in input_lower for word in ['good rating', 'good food']):
            parameters["min_food_satisfaction"] = SEMANTIC_THRESHOLDS["food_satisfaction"]["good"]["min_food_satisfaction"]
        elif any(word in input_lower for word in ['average rating', 'average food', 'okay food']):
            parameters.update(SEMANTIC_THRESHOLDS["food_satisfaction"]["average"])
        
        # Distance inference
        if any(word in input_lower for word in ['short-haul', 'short haul', 'short flight', 'short distance']):
            parameters["max_miles"] = SEMANTIC_THRESHOLDS["distance"]["short"]["max_miles"]
        elif any(word in input_lower for word in ['long-haul', 'long haul', 'long flight', 'long distance']):
            parameters["min_miles"] = SEMANTIC_THRESHOLDS["distance"]["long"]["min_miles"]
        elif any(word in input_lower for word in ['medium-haul', 'medium haul', 'medium distance']):
            parameters.update(SEMANTIC_THRESHOLDS["distance"]["medium"])
        
        # Legs inference
        if any(word in input_lower for word in ['direct flight', 'direct flights', 'nonstop', 'non-stop', 'non stop', 'single leg']):
            parameters["max_legs"] = SEMANTIC_THRESHOLDS["legs"]["direct"]["max_legs"]
        elif any(word in input_lower for word in ['connecting flight', 'multi-leg', 'multi leg', 'with connection', 'with stop']):
            parameters["min_legs"] = SEMANTIC_THRESHOLDS["legs"]["connecting"]["min_legs"]
        elif any(word in input_lower for word in ['complex journey', 'multiple stops', 'many legs']):
            parameters["min_legs"] = SEMANTIC_THRESHOLDS["legs"]["complex"]["min_legs"]
        
        return parameters


    def process_query(self, user_input):
        """
        Main processing pipeline that separates entities from parameters.
        Returns: (intent, entities, parameters)
        
        - entities: Core domain objects (airports, passengers, generations, loyalty tiers, etc.)
        - parameters: Numeric thresholds (min_delay, max_miles, etc.)
        """
        # Step 1: Classify intent
        intent = self.classify_intent(user_input)
        
        if intent == "unknown":
            return intent, {}, {}
        
        # Step 2: Extract entities (NER-based)
        entities = self.extract_entities(user_input, intent)
        
        # Step 3: Extract parameters
        # First try regex-based extraction for explicit numbers
        parameters = self.extract_parameters_from_text(user_input)
        
        # Then try semantic inference for qualitative terms
        semantic_params = self.infer_semantic_parameters(user_input)
        
        # Merge: explicit values take precedence
        for key, value in semantic_params.items():
            if key not in parameters:
                parameters[key] = value
        
        # If we still don't have parameters but the query seems to need them, use LLM
        needs_llm = any(word in user_input.lower() for word in [
            'severe', 'moderate', 'slight', 'extreme', 'poor', 'bad', 'good', 'excellent',
            'short', 'long', 'medium', 'direct', 'connecting', 'multi', 'complex'
        ])
        
        if needs_llm and not parameters:
            llm_params = self.extract_parameters_with_llm(user_input, intent)
            for key, value in llm_params.items():
                if key not in parameters:
                    parameters[key] = value
        
        return intent, entities, parameters

    def get_embedding(self, text):
        pass

def main():
    print("--- Airline System (NER + Parameter Inference Enabled) ---")
    retriever = Neo4jRetriever(default_driver)
    processor = QueryPreprocessor(retriever)
    
    while True:
        user_input = input("\n> ")
        if user_input.lower() in ['exit', 'quit']: break
            
        print("\n--- Processing Query ---")
        intent, entities, parameters = processor.process_query(user_input)
        
        print(f"Intent: {intent}")
        print(f"Entities: {entities}")
        print(f"Parameters: {parameters}")
        
        if intent == "unknown":
            print("Unknown intent.")
            continue
        
        # Merge entities and parameters for query execution
        # Parameters are separate from entities but passed together to the retriever
        combined = {**entities, **parameters}
        
        print("\nExecuting query...")
        results, query = retriever.run_query(intent, combined)
        
        print("\n--- Query Results ---")
        if isinstance(results, list):
            for res in results: print(res)
        else:
            print(results)


# Example test queries to try:
TEST_QUERIES = """
Test Queries to Try:
1. "Find severe delays for flights from LAX to IAX"
   -> Intent: analyze_delays, Entities: {origin: LAX, dest: IAX}, Parameters: {min_delay: 61}

2. "Show me journeys with poor food ratings"
   -> Intent: analyze_satisfaction, Parameters: {max_food_satisfaction: 2}

3. "List long-haul flights from EWX"
   -> Intent: search_network, Entities: {origin: EWX}, Parameters: {min_miles: 4000}

4. "Find direct flights from LAX to SFX"
   -> Intent: search_network, Entities: {origin: LAX, dest: SFX}, Parameters: {max_legs: 1}

5. "Show passengers with frequent severe delays"
   -> Intent: analyze_passengers, Parameters: {min_delay: 61}

6. "Find multi-leg journeys with delays over 30 minutes"
   -> Intent: analyze_journeys, Parameters: {min_legs: 2, min_delay: 30}
"""

if __name__ == "__main__":
    print(TEST_QUERIES)
    main()