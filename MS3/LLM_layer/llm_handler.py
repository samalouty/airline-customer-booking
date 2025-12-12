#!/usr/bin/env python3
"""
LLM Handler - Combines baseline and embedding results with structured prompts
"""
import os
import sys
import json
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from config.openai_client import get_answer, get_openai_gpt4_answer
from config.neo4j_client import driver as default_driver
from MS3.base_retrieve import Neo4jRetriever
from MS3.preprocessing import QueryPreprocessor


class LLMHandler:
    """
    Handles the LLM layer of the Graph-RAG pipeline.

    Features:
    1. Combines baseline (Cypher) and embedding-based retrieval
    2. Structures prompts with Context, Persona, and Task
    3. Supports multiple LLM models for comparison
    """

    def __init__(self, retriever=None, driver=None, embedding_model="BAAI/bge-m3"):
        """
        Initialize the LLM Handler.

        Args:
            retriever: Neo4jRetriever instance
            driver: Neo4j driver instance
            embedding_model: Name of the embedding model to use
        """
        self.retriever = retriever if retriever else Neo4jRetriever(driver if driver else default_driver)
        self.preprocessor = QueryPreprocessor(self.retriever)
        self.driver = driver if driver else default_driver

        # Load embedding model for semantic search on CPU to avoid CUDA OOM errors
        print(f"Loading embedding model: {embedding_model} (on CPU)")
        self.embedding_model = SentenceTransformer(embedding_model, device='cpu')
        self.embedding_index = self._get_index_for_model(embedding_model)

    def _get_index_for_model(self, model_name: str) -> str:
        """Map embedding model name to Neo4j index name"""
        if "minilm" in model_name.lower():
            return "minilm_vec_index"
        elif "mpnet" in model_name.lower():
            return "mpnet_vec_index"
        elif "bge-m3" in model_name.lower():
            return "bgem3_vec_index"
        else:
            return "bgem3_vec_index"  # Default to BGE-M3

    def get_baseline_results(self, user_query: str) -> Dict[str, Any]:
        """
        Get results using baseline Cypher queries.

        Args:
            user_query: The user's natural language query

        Returns:
            Dictionary containing intent, entities, and results
        """
        # Classify intent
        intent = self.preprocessor.classify_intent(user_query)

        # Extract entities
        entities = self.preprocessor.extract_entities(user_query, intent)

        # Run query
        results, cypher_query = self.retriever.run_query(intent, entities)

        return {
            "method": "baseline_cypher",
            "intent": intent,
            "entities": entities,
            "results": results,
            "query": user_query,
            "generated_cypher": cypher_query
        }

    def get_embedding_results(self, user_query: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Get results using embedding-based semantic search.

        Args:
            user_query: The user's natural language query
            top_k: Number of top results to retrieve

        Returns:
            Dictionary containing semantic search results
        """
        # Generate embedding for the query
        query_embedding = self.embedding_model.encode(user_query).tolist()

        # Search using vector index
        cypher = f"""
        CALL db.index.vector.queryNodes('{self.embedding_index}', $k, $vec)
        YIELD node, score

        MATCH (j:Journey)-[:HAS_VECTOR]->(node)
        MATCH (p:Passenger)-[:TOOK]->(j)
        MATCH (j)-[:ON]->(f:Flight)
        MATCH (f)-[:DEPARTS_FROM]->(origin:Airport)
        MATCH (f)-[:ARRIVES_AT]->(dest:Airport)

        RETURN
            score,
            node.text AS semantic_text,
            j.feedback_ID AS feedback_id,
            j.arrival_delay_minutes AS delay,
            j.food_satisfaction_score AS food_score,
            j.actual_flown_miles AS miles,
            j.passenger_class AS class,
            p.generation AS generation,
            p.loyalty_program_level AS loyalty,
            f.flight_number AS flight_number,
            f.fleet_type_description AS aircraft,
            origin.station_code AS origin,
            dest.station_code AS destination
        ORDER BY score DESC
        LIMIT $k
        """

        try:
            with self.driver.session() as session:
                result = session.run(cypher, k=top_k, vec=query_embedding)
                records = [dict(r) for r in result]
        except Exception as e:
            records = []
            print(f"Embedding search error: {e}")

        return {
            "method": "embedding_semantic_search",
            "results": records,
            "query": user_query,
            "top_k": top_k
        }

    def get_automated_query_results(self, user_query: str) -> Dict[str, Any]:
        """
        Get results by dynamically generating a Cypher query using GPT-4o.
        """
        schema_desc = """
        Nodes & Properties:
        - Passenger: generation, loyalty_program_level, record_locator
        - Journey: arrival_delay_minutes, food_satisfaction_score, passenger_class, feedback_ID, actual_flown_miles
        - Flight: flight_number, fleet_type_description
        - Airport: station_code

        Relationships:
        - (:Passenger)-[:TOOK]->(:Journey)
        - (:Journey)-[:ON]->(:Flight)
        - (:Flight)-[:DEPARTS_FROM]->(:Airport)
        - (:Flight)-[:ARRIVES_AT]->(:Airport)
        """

        prompt = f"""You are a Neo4j Cypher expert. 
        Generate a READ-ONLY Cypher query for the following user question based on the schema below.
        
        SCHEMA:
        {schema_desc}

        RULES:
        1. Return ONLY the Cypher query. No markdown, no explanations.
        2. Use Case-Insensitive matching for strings if unsure (e.g. toLower(n.prop) CONTAINS 'value')
        3. LIMIT results to 20 unless specified otherwise.
        4. Do NOT use procedures like APOC.
        5. For aggregations (averages, counts), return clear aliases.

        User Question: {user_query}
        """

        # Call GPT-4o to generate query
        generated_cypher = get_openai_gpt4_answer(prompt)
        
        # Clean potential markdown
        generated_cypher = generated_cypher.replace("```cypher", "").replace("```", "").strip()

        if "Error" in generated_cypher:
            return {
                "method": "automated_cypher",
                "results": [],
                "error": generated_cypher,
                "generated_cypher": None
            }

        # Execute Query
        results = []
        try:
            with self.driver.session() as session:
                res = session.run(generated_cypher)
                # Serialize results: Convert Nodes/Relationships to dicts
                for record in res:
                    row = {}
                    for key, value in record.items():
                        if hasattr(value, 'items') and callable(value.items):
                             row[key] = dict(value.items())
                        else:
                             row[key] = value
                    results.append(row)
        except Exception as e:
            return {
                "method": "automated_cypher",
                "results": [],
                "error": str(e),
                "generated_cypher": generated_cypher
            }
            
        return {
            "method": "automated_cypher",
            "results": results,
            "generated_cypher": generated_cypher
        }

    def combine_results(self, baseline_results: Dict, embedding_results: Dict, automated_results: Dict = None) -> Dict[str, Any]:
        """
        Combine results from baseline, embedding, and automation methods.

        Strategy:
        - Remove duplicates (by feedback_ID if available)
        - Prioritize baseline for exact matches
        - Add embedding results for semantic context
        - Rank by relevance

        Args:
            baseline_results: Results from Cypher queries
            embedding_results: Results from semantic search
            automated_results: Results from automated Cypher generation (Optional)

        Returns:
            Combined and deduplicated results
        """
        combined = {
            "baseline": baseline_results,
            "embedding": embedding_results,
            "automation": automated_results if automated_results else {},
            "merged_data": []
        }

        # Track seen feedback IDs to avoid duplicates
        seen_ids = set()

        # Helper to process a list of results
        def process_list(source_name, data_list, score_key=None):
            if isinstance(data_list, list) and data_list:
                for item in data_list:
                    # Try to find a unique ID
                    item_id = item.get('feedback_ID') or item.get('feedback_id') or str(item)
                    
                    # For simple aggregations (no IDs), always add them
                    if not (item.get('feedback_ID') or item.get('feedback_id')):
                         combined["merged_data"].append({
                            "source": source_name,
                            "data": item
                        })
                    elif item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        entry = {"source": source_name, "data": item}
                        if score_key and score_key in item:
                            entry["score"] = item[score_key]
                        combined["merged_data"].append(entry)

        # 1. Add Automation Results (High Priority - Dynamic)
        if automated_results:
             process_list("automation", automated_results.get("results", []))

        # 2. Add Baseline Results (Medium Priority - Fixed Templates)

        # Add baseline results first (they're exact matches)
        # 2. Add Baseline Results (Medium Priority - Fixed Templates)
        baseline_data = baseline_results.get("results", [])
        process_list("baseline", baseline_data)

        # 3. Add Embedding Results (Lower Priority - Contextual)
        embedding_data = embedding_results.get("results", [])
        process_list("embedding", embedding_data, score_key="score")

        return combined

    def format_context(self, combined_results: Dict) -> str:
        """
        Format the combined results into a readable context string for the LLM.

        Args:
            combined_results: Combined results from both methods

        Returns:
            Formatted context string
        """
        context_parts = []

        # Baseline results - present as "Database Query Results" without technical details
        baseline = combined_results["baseline"]
        if baseline.get("results"):
            context_parts.append("=== FLIGHT DATABASE INFORMATION ===")
            context_parts.append(f"Query Results: {json.dumps(baseline['results'], indent=2)}")

        # Automation results
        automation = combined_results.get("automation", {})
        if automation.get("results"):
            context_parts.append("=== AUTOMATED QUERY RESULTS (GPT-4o Generated) ===")
            context_parts.append(f"Generated Cypher: {automation.get('generated_cypher')}")
            context_parts.append(f"Results: {json.dumps(automation['results'], indent=2)}")

        # Embedding results - present as "Related Flight Information" without scores
        embedding = combined_results["embedding"]
        if embedding.get("results"):
            context_parts.append("\n=== RELATED FLIGHT INFORMATION ===")
            for i, result in enumerate(embedding["results"][:3], 1):  # Top 3
                context_parts.append(f"\n--- Flight Record {i} ---")
                if result.get('semantic_text'):
                    context_parts.append(f"Summary: {result.get('semantic_text')}")
                context_parts.append(f"Flight {result.get('flight_number')}: "
                                   f"{result.get('origin')} → {result.get('destination')}, "
                                   f"Aircraft: {result.get('aircraft')}, "
                                   f"Arrival: {result.get('delay')} min {'early' if result.get('delay', 0) < 0 else 'delay' if result.get('delay', 0) > 0 else 'on time'}, "
                                   f"Food Rating: {result.get('food_score')}/5, "
                                   f"Passenger: {result.get('generation')}, {result.get('loyalty')}")

        return "\n".join(context_parts) if context_parts else "No relevant data found."

    def create_structured_prompt(self, user_query: str, context: str, persona: str = None) -> str:
        """
        Create a structured prompt with Context, Persona, and Task.

        Args:
            user_query: The user's question
            context: The formatted context from KG retrieval
            persona: Optional custom persona (default: airline insights assistant)

        Returns:
            Structured prompt string
        """
        # Default persona for airline theme
        if not persona:
            persona = """You are a Senior Airline Business Intelligence Analyst presenting insights to airline executives and operations managers.
Your role is to transform flight data, passenger feedback, and operational metrics into actionable business insights that drive strategic decisions.

Your expertise includes:
- Revenue optimization and passenger yield analysis
- Route performance and network planning
- Customer satisfaction drivers and loyalty program effectiveness
- Operational efficiency, on-time performance, and delay root causes
- Fleet utilization and aircraft performance comparisons
- Competitive positioning and market share analysis

Communication style:
- Present findings as strategic business insights, not raw data
- Highlight trends, patterns, and anomalies that impact the bottom line
- Recommend specific actions based on the data
- Quantify business impact when possible (e.g., "This affects X% of passengers")
- Use airline industry terminology appropriately"""

        task = f"""Analyze the provided data and deliver business insights for airline management.

CRITICAL RULES:
- NEVER mention technical terms like "intents", "entities", "embeddings", "semantic search", "vector scores", or "knowledge graph"
- NEVER display raw data structures, JSON, scores, or internal system details
- NEVER say "based on the data provided" or reference how you retrieved information
- DO present insights as if you analyzed this data yourself

Question: {user_query}

Your response MUST:
1. Lead with the key business insight or finding
2. Support with specific data points woven naturally into the narrative
3. Explain the business implications (why this matters to the airline)
4. Provide actionable recommendations when relevant
5. Identify any concerning trends or opportunities for improvement

Format your response as a professional business insight brief - concise, data-driven, and focused on what matters for airline operations and profitability."""
        
        prompt = f"""### PERSONA
{persona}

### CONTEXT (Knowledge Graph Data)
{context}

### TASK
{task}

### ANSWER
"""
        return prompt

    def generate_answer(self, user_query: str, model: str = "llama-3.1-8b-instant",
                       temperature: float = 0.1, retrieval_mode: str = "baseline", use_embeddings: bool = False) -> Dict[str, Any]:
        """
        Generate a complete answer using the Graph-RAG pipeline.

        Args:
            user_query: The user's natural language query
            model: LLM model to use
            temperature: Temperature for generation
            # mode: 'baseline', 'embedding', 'hybrid', 'automation', 'all'
            retrieval_mode: str = 'baseline' 
            use_embeddings: bool = True # Deprecated, kept for backward compat

        Returns:
            Dictionary containing query, context, prompt, and answer
        """
        # Initialize result containers
        baseline_results = {}
        embedding_results = {}
        automated_results = {}

        # 1. Baseline logic
        if retrieval_mode in ['baseline', 'hybrid', 'all']:
             baseline_results = self.get_baseline_results(user_query)

        # 2. Embedding logic
        if retrieval_mode in ['embedding', 'hybrid', 'all'] or (retrieval_mode == 'baseline' and use_embeddings): # Handle legacy flag
             embedding_results = self.get_embedding_results(user_query)

        # 3. Automation logic (New)
        if retrieval_mode in ['automation', 'all']:
             automated_results = self.get_automated_query_results(user_query)

        # Step 3: Combine results
        combined_results = self.combine_results(baseline_results, embedding_results, automated_results)

        # Step 4: Format context
        context = self.format_context(combined_results)

        # Step 5: Create structured prompt
        prompt = self.create_structured_prompt(user_query, context)

        # Step 6: Get LLM response
        try:
            answer = get_answer(prompt, model=model, temperature=temperature)
        except Exception as e:
            answer = f"Error generating answer: {e}"

        return {
            "query": user_query,
            "baseline_results": baseline_results,
            "embedding_results": embedding_results,
            "automated_results": automated_results,
            "combined_results": combined_results,
            "context": context,
            "prompt": prompt,
            "answer": answer,
            "model": model
        }


# Test the LLM Handler
if __name__ == "__main__":
    print("Initializing LLM Handler...")
    handler = LLMHandler()

    # Test query
    test_query = "Which aircraft types have the highest average delay?"

    print(f"\nTest Query: {test_query}")
    print("="*80)

    result = handler.generate_answer(test_query)

    print("\n--- CONTEXT ---")
    print(result["context"])

    print("\n--- ANSWER ---")
    print(result["answer"])