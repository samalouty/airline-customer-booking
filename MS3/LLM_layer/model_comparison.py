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

    # Available models - synced with app.py LLM_MODELS
    MODELS = {
        # Recommended Models
        "llama-3.1-8b-instant": {
            "name": "Llama 3.1 8B (Fast)",
            "description": "Fast, reliable, low cost"
        },
        "llama-3.3-70b-versatile": {
            "name": "Llama 3.3 70B (Versatile)",
            "description": "High quality, versatile"
        },

        # Llama 4 Series
        "meta-llama/llama-4-scout-17b-16e-instruct": {
            "name": "Llama 4 Scout",
            "description": "Vision capable, 10M context"
        },
        # Reasoning Models
        "qwen/qwen3-32b": {
            "name": "Qwen 3 32B",
            "description": "Strong performance, emerging model"
        },

        # GPT OSS Models
        "openai/gpt-oss-20b": {
            "name": "GPT OSS 20B",
            "description": "Balanced open-source model"
        },
        "openai/gpt-oss-120b": {
            "name": "GPT OSS 120B",
            "description": "Large scale open-source model"
        },

        "moonshotai/kimi-k2-instruct-0905": {
            "name": "Kimi K2 Instruct",
            "description": "High quality open-source model"
        }
    }

    def __init__(self, llm_handler: LLMHandler = None, test_results_path: str = None):
        """
        Initialize the model comparator.

        Args:
            llm_handler: LLMHandler instance (creates new one if not provided)
            test_results_path: Path to test_results_final.json for accuracy comparison
        """
        self.handler = llm_handler if llm_handler else LLMHandler()
        self.results = []
        self.expected_results = {}

        # Load expected results if path provided
        if test_results_path is None:
            # Default path
            script_dir = os.path.dirname(os.path.abspath(__file__))
            test_results_path = os.path.join(script_dir, '..', 'test_results_final.json')

        if os.path.exists(test_results_path):
            self.load_expected_results(test_results_path)

    def load_expected_results(self, filepath: str):
        """
        Load expected results from test_results_final.json.

        Args:
            filepath: Path to the test results JSON file
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Create a mapping from question_text to expected results
            for result in data.get('results', []):
                question = result.get('question_text', '').strip()
                if question:
                    self.expected_results[question] = {
                        'question_id': result.get('question_id'),
                        'intent': result.get('intent'),
                        'success': result.get('success', False),
                        'query_results': result.get('query_results', []),
                        'result_count': result.get('result_count', 0)
                    }

            print(f"✓ Loaded {len(self.expected_results)} expected results from test file")
        except Exception as e:
            print(f"⚠ Could not load expected results: {e}")
            self.expected_results = {}

    def compare_with_expected(self, query: str, actual_result: Dict) -> Dict[str, Any]:
        """
        Compare actual model result with expected result from test_results_final.json.

        Args:
            query: The query text
            actual_result: The result from the model

        Returns:
            Comparison metrics including accuracy
        """
        expected = self.expected_results.get(query.strip())

        if not expected:
            return {
                'has_expected': False,
                'matches_expected': None,
                'note': 'No expected result found for this query'
            }

        # Get actual intent and results
        actual_intent = actual_result.get('baseline_results', {}).get('intent')
        actual_query_results = actual_result.get('baseline_results', {}).get('results', [])
        actual_result_count = len(actual_query_results) if isinstance(actual_query_results, list) else 0

        # Compare intent
        intent_match = actual_intent == expected['intent']

        # Compare result count (similar count indicates similar query execution)
        result_count_match = actual_result_count == expected['result_count']

        # If expected test was successful, check if we got similar results
        matches_expected = (
            intent_match and
            (result_count_match or abs(actual_result_count - expected['result_count']) <= 2) and
            actual_result_count > 0
        )

        return {
            'has_expected': True,
            'matches_expected': matches_expected,
            'expected_intent': expected['intent'],
            'actual_intent': actual_intent,
            'intent_match': intent_match,
            'expected_result_count': expected['result_count'],
            'actual_result_count': actual_result_count,
            'result_count_match': result_count_match,
            'expected_success': expected['success']
        }

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
            # model_key is now the full model ID (e.g., "llama-3.1-8b-instant")
            model_info = self.MODELS.get(model_key, {})
            model_display_name = model_info.get("name", model_key)

            print(f"\nTesting model: {model_display_name} ({model_key})")

            try:
                # Measure response time
                start_time = time.time()

                result = self.handler.generate_answer(
                    user_query=query,
                    model=model_key,
                    temperature=0.1,
                    use_embeddings=use_embeddings
                )

                response_time = time.time() - start_time

                # Extract metrics
                answer = result["answer"]
                answer_length = len(answer) if answer else 0
                word_count = len(answer.split()) if answer else 0

                # Compare with expected results
                accuracy_check = self.compare_with_expected(query, result)

                comparison["models"][model_key] = {
                    "model_name": model_display_name,
                    "model_id": model_key,
                    "answer": answer,
                    "response_time": response_time,
                    "answer_length": answer_length,
                    "word_count": word_count,
                    "context_length": len(result.get("context", "")),
                    "baseline_results_count": len(result.get("baseline_results", {}).get("results", [])),
                    "embedding_results_count": len(result.get("embedding_results", {}).get("results", [])),
                    "accuracy_check": accuracy_check,
                    "correct": accuracy_check.get('matches_expected', False),
                    "error": None
                }

                match_indicator = "✓" if accuracy_check.get('matches_expected') else "✗"
                print(f"{match_indicator} Response time: {response_time:.2f}s | Words: {word_count} | Correct: {accuracy_check.get('matches_expected', 'N/A')}")

            except Exception as e:
                print(f"✗ Error: {e}")
                comparison["models"][model_key] = {
                    "model_name": model_display_name,
                    "model_id": model_key,
                    "answer": None,
                    "response_time": None,
                    "accuracy_check": {'has_expected': False, 'matches_expected': False},
                    "correct": False,
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
            all_attempts = []

            for result in self.results:
                if model_key in result["models"]:
                    model_result = result["models"][model_key]
                    all_attempts.append(model_result)
                    if model_result["response_time"] is not None:
                        model_data.append(model_result)

            if model_data:
                avg_response_time = sum(d["response_time"] for d in model_data) / len(model_data)
                avg_word_count = sum(d["word_count"] for d in model_data) / len(model_data)
                success_rate = len(model_data) / len(self.results)

                # Calculate accuracy based on comparison with expected results
                correct_count = sum(1 for d in all_attempts if d.get("correct", False))
                accuracy = correct_count / len(all_attempts) if all_attempts else 0

                # Count queries with expected results available
                queries_with_expected = sum(1 for d in all_attempts
                                          if d.get("accuracy_check", {}).get("has_expected", False))

                summary["models"][model_key] = {
                    "total_queries": len(model_data),
                    "success_rate": success_rate,
                    "accuracy": accuracy,
                    "correct_count": correct_count,
                    "queries_with_expected": queries_with_expected,
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
        print("-"*100)
        print(f"{'Model':<30} {'Accuracy':<12} {'Success':<10} {'Avg Time':<12} {'Avg Words':<12}")
        print("-"*100)

        for model_key, stats in summary["models"].items():
            # Get model display name from MODELS dict
            model_info = self.MODELS.get(model_key, {})
            display_name = model_info.get("name", model_key)[:28]

            print(f"{display_name:<30} "
                  f"{stats['accuracy']*100:>6.1f}%     "
                  f"{stats['success_rate']*100:>6.1f}%   "
                  f"{stats['avg_response_time']:>8.2f}s    "
                  f"{stats['avg_word_count']:>8.1f}")

        print("-"*100)
        print(f"\nNote: Accuracy shows correct answers vs. test_results_final.json")
        print(f"      Success shows queries that completed without errors")


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

    # Models to test (using model IDs from MODELS dictionary)
    test_models = ["openai/gpt-oss-20b", "moonshotai/kimi-k2-instruct-0905", "qwen/qwen3-32b"]

    # Run comparison
    comparator.run_batch_comparison(test_queries, test_models)

    # Print summary
    comparator.print_summary()

    # Save results
    comparator.save_results()