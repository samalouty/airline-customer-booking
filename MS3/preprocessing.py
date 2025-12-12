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
                {"label": "LOYALTY_TIER", "pattern": [{"LOWER": "non"}, {"LOWER": "elite"}]},

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
        Return ONLY the intent key. Default to "unknown".
        """
        intent = get_answer(prompt).strip().replace('"', '').replace("'", "")
        return intent if intent in available_intents else "unknown"


    def extract_entities(self, user_input, intent):
        """
        REPLACED LLM with spaCy NER Pipeline.
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
                entities["generation"] = val
            
            elif ent.label_ == "LOYALTY_TIER":
                entities["loyalty_tier"] = val.lower() # DB likely stores lowercase or specific format
            
            elif ent.label_ == "CLASS":
                entities["class"] = val.title() # e.g., "Economy"
            
            elif ent.label_ == "FLEET":
                entities["fleet_type"] = val.upper()
            
            elif ent.label_ == "LOCATOR":
                entities["record_locator"] = val
            
            elif ent.label_ == "AIRPORT":
                # Logic to distinguish Origin vs Dest based on prepositions
                # Look at the word immediately 'before' the airport code
                token_index = ent.start
                if token_index > 0:
                    prev_word = doc[token_index - 1].text.lower()
                    if prev_word in ["from", "departing", "out"]:
                        entities["origin"] = val
                    elif prev_word in ["to", "arriving", "into"]:
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

        # --- 2. Numerical extraction (Min/Max Logic) ---
        # This is harder for simple NER, so we use Regex + Dependency logic
        # Example: "longer than 2000 miles" or "delays over 60 min"
        
        # Regex for Mileage
        miles_match = re.search(r'(longer|greater|more) than (\d+)', user_input)
        if miles_match:
            entities["min_miles"] = int(miles_match.group(2))

        # Regex for Delays
        delay_match = re.search(r'(delay|late).*?(\d+)', user_input)
        if delay_match:
            # Simple assumption: users usually ask for delays GREATER than X
            entities["min_delay"] = int(delay_match.group(2))
            
        # Regex for Satisfaction Scores
        score_match = re.search(r'(rating|score).*?(\d)', user_input) # Single digit for score
        if score_match:
            score = int(score_match.group(2))
            # Determine if they want 'poor' (<) or 'good' (>)
            if "poor" in user_input or "bad" in user_input or "less" in user_input or "under" in user_input:
                entities["max_score"] = score
            else:
                entities["min_score"] = score

        return entities

    def get_embedding(self, text):
        pass

def main():
    print("--- Airline System (NER Enabled) ---")
    retriever = Neo4jRetriever(default_driver)
    processor = QueryPreprocessor(retriever)
    
    while True:
        user_input = input("\n> ")
        if user_input.lower() in ['exit', 'quit']: break
            
        print("Classifying intent (LLM)...")
        intent = processor.classify_intent(user_input)
        print(f"Identified Intent: {intent}")
        
        if intent == "unknown":
            print("Unknown intent.")
            continue
            
        print("Extracting entities (NER)...")
        entities = processor.extract_entities(user_input, intent)
        print(f"Extracted Entities: {entities}")
        
        print("Executing query...")
        results, query = retriever.run_query(intent, entities)
        
        print("\n--- Query Results ---")
        if isinstance(results, list):
            for res in results: print(res)
        else:
            print(results)

if __name__ == "__main__":
    main()