#!/usr/bin/env python3
"""
Model Comparison Framework
Compares multiple LLM models on the same queries
"""
import os
import sys
import time
import json
from typing import List, Dict, Any
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from MS3.LLM_layer.llm_handler import LLMHandler


class ModelComparator:
    """
    Compares multiple LLM models on airline queries.

    Supports:
    - Multiple model testing
    - Quantitative metrics (response time, token usage)
    - Qualitative comparison (answer quality)
    """

    # Available models through Groq API (Updated December 2024)
    # Note: Some models have been decommissioned by Groq
    MODELS = {
        # RECOMMENDED: Fast & Production-Ready
        "llama-3.1-8b": "llama-3.1-8b-instant",          # ✅ Fast, reliable, low cost
        "llama-3.3-70b": "llama-3.3-70b-versatile",      # ✅ High quality, versatile
        
        # Llama 4 (Vision & Multimodal - NEW)
        "llama-4-scout": "meta-llama/llama-4-scout-17b-16e-instruct",      # ✅ Vision, 10M context
        "llama-4-maverick": "meta-llama/llama-4-maverick-17b-128e-instruct", # ✅ Vision, advanced
        
        # Reasoning Models (Chain-of-Thought)
        "deepseek-r1": "deepseek-r1-distill-llama-70b",  # ✅ Strong reasoning
        "qwen3-32b": "qwen/qwen3-32b" ,

        "gpt-oss-20b": "openai/gpt-oss-20b",            # ✅ Balanced
        "gpt-oss-120b": "openai/gpt-oss-120b",          # ✅ Larger model
        
        
        # Default (most reliable)
        "default": "llama-3.1-8b-instant"
    }

    def __init__(self, llm_handler: LLMHandler = None):
        """
        Initialize the model comparator.

        Args:
            llm_handler: LLMHandler instance (creates new one if not provided)
        """
        self.handler = llm_handler if llm_handler else LLMHandler()
        self.results = []

    def run_single_comparison(self, query: str, models: List[str],
                            use_embeddings: bool = True) -> Dict[str, Any]:
        """
        Run a single query across multiple models.

        Args:
            query: The test query
            models: List of model names to test
            use_embeddings: Whether to use embedding-based retrieval

        Returns:
            Comparison results for this query
        """
        comparison = {
            "query": query,
            "timestamp": datetime.now().isoformat(),
            "use_embeddings": use_embeddings,
            "models": {}
        }

        print(f"\n{'='*80}")
        print(f"Query: {query}")
        print(f"{'='*80}")

        for model_key in models:
            model_name = self.MODELS.get(model_key, model_key)

            print(f"\nTesting model: {model_key} ({model_name})")

            try:
                # Measure response time
                start_time = time.time()

                result = self.handler.generate_answer(
                    user_query=query,
                    model=model_name,
                    temperature=0.1,
                    use_embeddings=use_embeddings
                )

                response_time = time.time() - start_time

                # Extract metrics
                answer = result["answer"]
                answer_length = len(answer) if answer else 0
                word_count = len(answer.split()) if answer else 0

                comparison["models"][model_key] = {
                    "model_name": model_name,
                    "answer": answer,
                    "response_time": response_time,
                    "answer_length": answer_length,
                    "word_count": word_count,
                    "context_length": len(result.get("context", "")),
                    "baseline_results_count": len(result.get("baseline_results", {}).get("results", [])),
                    "embedding_results_count": len(result.get("embedding_results", {}).get("results", [])),
                    "error": None
                }

                print(f"✓ Response time: {response_time:.2f}s | Words: {word_count}")

            except Exception as e:
                print(f"✗ Error: {e}")
                comparison["models"][model_key] = {
                    "model_name": model_name,
                    "answer": None,
                    "response_time": None,
                    "error": str(e)
                }

        return comparison

    def run_batch_comparison(self, queries: List[str], models: List[str],
                           use_embeddings: bool = True) -> List[Dict[str, Any]]:
        """
        Run multiple queries across multiple models.

        Args:
            queries: List of test queries
            models: List of model names to test
            use_embeddings: Whether to use embedding-based retrieval

        Returns:
            List of comparison results
        """
        results = []

        print(f"\n{'#'*80}")
        print(f"BATCH COMPARISON: {len(queries)} queries × {len(models)} models")
        print(f"{'#'*80}")

        for i, query in enumerate(queries, 1):
            print(f"\n[Query {i}/{len(queries)}]")
            comparison = self.run_single_comparison(query, models, use_embeddings)
            results.append(comparison)

        self.results = results
        return results

    def generate_summary(self) -> Dict[str, Any]:
        """
        Generate summary statistics from all comparisons.

        Returns:
            Summary statistics dictionary
        """
        if not self.results:
            return {"error": "No results to summarize. Run comparisons first."}

        summary = {
            "total_queries": len(self.results),
            "models": {},
            "timestamp": datetime.now().isoformat()
        }

        # Collect all model keys
        all_models = set()
        for result in self.results:
            all_models.update(result["models"].keys())

        # Calculate statistics per model
        for model_key in all_models:
            model_data = []

            for result in self.results:
                if model_key in result["models"]:
                    model_result = result["models"][model_key]
                    if model_result["response_time"] is not None:
                        model_data.append(model_result)

            if model_data:
                avg_response_time = sum(d["response_time"] for d in model_data) / len(model_data)
                avg_word_count = sum(d["word_count"] for d in model_data) / len(model_data)
                success_rate = len(model_data) / len(self.results)

                summary["models"][model_key] = {
                    "total_queries": len(model_data),
                    "success_rate": success_rate,
                    "avg_response_time": avg_response_time,
                    "avg_word_count": avg_word_count,
                    "min_response_time": min(d["response_time"] for d in model_data),
                    "max_response_time": max(d["response_time"] for d in model_data)
                }

        return summary

    def save_results(self, filename: str = "model_comparison_results.json"):
        """
        Save comparison results to a JSON file.

        Args:
            filename: Output filename
        """
        output = {
            "summary": self.generate_summary(),
            "detailed_results": self.results
        }

        filepath = os.path.join(os.path.dirname(__file__), filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\nResults saved to: {filepath}")

    def print_summary(self):
        """Print a formatted summary of the comparison results."""
        summary = self.generate_summary()

        print("\n" + "="*80)
        print("MODEL COMPARISON SUMMARY")
        print("="*80)

        print(f"\nTotal Queries: {summary['total_queries']}")
        print(f"\nModel Performance:")
        print("-"*80)
        print(f"{'Model':<20} {'Success':<10} {'Avg Time':<12} {'Avg Words':<12}")
        print("-"*80)

        for model_key, stats in summary["models"].items():
            print(f"{model_key:<20} "
                  f"{stats['success_rate']*100:>6.1f}%   "
                  f"{stats['avg_response_time']:>8.2f}s    "
                  f"{stats['avg_word_count']:>8.1f}")

        print("-"*80)


# Test the comparator
if __name__ == "__main__":
    print("Initializing Model Comparator...")

    comparator = ModelComparator()

    # Test queries
    test_queries = [
        "Which aircraft types have the highest average delay?",
        "How do Boomers rate the food service?",
        "Show me flights with severe delays and poor food ratings."
    ]

    # Models to test (using active free Groq models)
    test_models = ["gpt-oss-20b", "kimi-k2", "qwen3-32b"]

    # Run comparison
    comparator.run_batch_comparison(test_queries, test_models)

    # Print summary
    comparator.print_summary()

    # Save results
    comparator.save_results()