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

from config.openai_client import get_answer
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

    def combine_results(self, baseline_results: Dict, embedding_results: Dict) -> Dict[str, Any]:
        """
        Combine results from baseline and embedding methods.

        Strategy:
        - Remove duplicates (by feedback_ID if available)
        - Prioritize baseline for exact matches
        - Add embedding results for semantic context
        - Rank by relevance

        Args:
            baseline_results: Results from Cypher queries
            embedding_results: Results from semantic search

        Returns:
            Combined and deduplicated results
        """
        combined = {
            "baseline": baseline_results,
            "embedding": embedding_results,
            "merged_data": []
        }

        # Track seen feedback IDs to avoid duplicates
        seen_ids = set()

        # Add baseline results first (they're exact matches)
        baseline_data = baseline_results.get("results", [])
        if isinstance(baseline_data, list) and baseline_data:
            for item in baseline_data:
                # Extract feedback_ID if available
                feedback_id = item.get('feedback_ID') or item.get('feedback_id')
                if feedback_id and feedback_id not in seen_ids:
                    seen_ids.add(feedback_id)
                    combined["merged_data"].append({
                        "source": "baseline",
                        "data": item
                    })

        # Add embedding results (for semantic context)
        embedding_data = embedding_results.get("results", [])
        if isinstance(embedding_data, list):
            for item in embedding_data:
                feedback_id = item.get('feedback_id')
                if feedback_id and feedback_id not in seen_ids:
                    seen_ids.add(feedback_id)
                    combined["merged_data"].append({
                        "source": "embedding",
                        "data": item,
                        "score": item.get("score", 0)
                    })

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

        # Baseline results
        baseline = combined_results["baseline"]
        if baseline.get("results"):
            context_parts.append("=== STRUCTURED QUERY RESULTS ===")
            context_parts.append(f"Intent: {baseline.get('intent')}")
            context_parts.append(f"Entities: {baseline.get('entities')}")
            context_parts.append(f"Results: {json.dumps(baseline['results'], indent=2)}")

        # Embedding results
        embedding = combined_results["embedding"]
        if embedding.get("results"):
            context_parts.append("\n=== SEMANTIC SEARCH RESULTS ===")
            for i, result in enumerate(embedding["results"][:3], 1):  # Top 3
                context_parts.append(f"\n--- Match {i} (Score: {result.get('score', 0):.3f}) ---")
                context_parts.append(result.get('semantic_text', 'N/A'))
                context_parts.append(f"Details: Flight {result.get('flight_number')}, "
                                   f"{result.get('origin')} → {result.get('destination')}, "
                                   f"Delay: {result.get('delay')}min, "
                                   f"Food: {result.get('food_score')}/5")

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
            persona = """You are an Airline Flight Insights Assistant working for the airline company.
Your role is to analyze flight data, passenger feedback, and operational metrics to provide
actionable insights for improving airline operations and customer satisfaction.
You speak professionally and focus on data-driven insights."""

        task = f"""Answer the following question using ONLY the provided information from the knowledge graph.
Do not make up information or hallucinate. If the data doesn't contain the answer, say so clearly.

Question: {user_query}

Provide a clear, concise answer that:
1. Directly addresses the question
2. References specific data points from the context
3. Provides actionable insights when relevant
4. Uses a professional tone appropriate for airline management"""

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
                       temperature: float = 0.1, use_embeddings: bool = True) -> Dict[str, Any]:
        """
        Generate a complete answer using the Graph-RAG pipeline.

        Args:
            user_query: The user's natural language query
            model: LLM model to use
            temperature: Temperature for generation
            use_embeddings: Whether to include embedding results

        Returns:
            Dictionary containing query, context, prompt, and answer
        """
        # Step 1: Get baseline results
        baseline_results = self.get_baseline_results(user_query)

        # Step 2: Get embedding results (if enabled)
        embedding_results = {}
        if use_embeddings:
            embedding_results = self.get_embedding_results(user_query)

        # Step 3: Combine results
        combined_results = self.combine_results(baseline_results, embedding_results)

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