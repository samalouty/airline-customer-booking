#!/usr/bin/env python3
"""
Test Script for LLM Layer
Uses the 10 test questions to evaluate the complete Graph-RAG pipeline
"""
import os
import sys
import json
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from MS3.LLM_layer.llm_handler import LLMHandler
from MS3.LLM_layer.model_comparison import ModelComparator
from MS3.LLM_layer.evaluation import EvaluationMetrics


def load_test_questions(filepath: str = "../ten_q.txt") -> list:
    """
    Load test questions from ten_q.txt file.

    Args:
        filepath: Path to the test questions file

    Returns:
        List of question strings
    """
    questions = []

    full_path = os.path.join(os.path.dirname(__file__), filepath)

    with open(full_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_question = ""
    for line in lines:
        line = line.strip()

        # Skip empty lines and Cypher queries
        if not line or line.startswith("MATCH") or line.startswith("WITH") or line.startswith("WHERE") or line.startswith("RETURN") or line.startswith("ORDER") or line.startswith("LIMIT") or line.startswith("OPTIONAL"):
            continue

        # Check if it's a question line
        if line.startswith("Q") and "." in line[:5]:
            # Extract question text (after "Q1. " or "Q10. ")
            parts = line.split(".", 1)
            if len(parts) > 1:
                question = parts[1].strip()
                if question and not question.startswith("Q"):  # Avoid empty or nested Qs
                    questions.append(question)

    return questions


def test_single_query():
    """Test a single query through the complete pipeline."""
    print("="*80)
    print("TEST 1: Single Query Test")
    print("="*80)

    handler = LLMHandler()

    query = "Which aircraft types have the highest average delay?"
    print(f"\nQuery: {query}")

    result = handler.generate_answer(query)

    print("\n--- Baseline Results ---")
    print(f"Intent: {result['baseline_results']['intent']}")
    print(f"Entities: {result['baseline_results']['entities']}")
    print(f"Results Count: {len(result['baseline_results'].get('results', []))}")

    print("\n--- Embedding Results ---")
    print(f"Results Count: {len(result['embedding_results'].get('results', []))}")

    print("\n--- Context (Truncated) ---")
    print(result['context'][:500] + "..." if len(result['context']) > 500 else result['context'])

    print("\n--- Final Answer ---")
    print(result['answer'])

    return result


def test_model_comparison():
    """Test model comparison with multiple queries."""
    print("\n" + "="*80)
    print("TEST 2: Model Comparison Test")
    print("="*80)

    # Load test questions
    questions = load_test_questions()
    print(f"\nLoaded {len(questions)} test questions")

    # Use first 5 questions for faster testing
    # test_questions = questions[:2]
    test_questions = questions

    # Models to compare (using free Groq models)
    models_to_test = ["gpt-oss-20b", "llama-3.3-70b", "qwen3-32b"]
    # models_to_test = ["llama-3.3-70b"]

    print(f"\nTesting {len(test_questions)} questions across {len(models_to_test)} models")
    print(f"Models: {models_to_test}")

    # Run comparison
    comparator = ModelComparator()
    results = comparator.run_batch_comparison(test_questions, models_to_test, use_embeddings=True)

    # Print summary
    comparator.print_summary()

    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"comparison_results_{timestamp}.json"
    comparator.save_results(filename)

    return comparator, results


def test_evaluation(comparator, results):
    """Test evaluation framework."""
    print("\n" + "="*80)
    print("TEST 3: Evaluation Framework Test")
    print("="*80)

    evaluator = EvaluationMetrics()

    # Evaluate the comparison results
    report = evaluator.evaluate_comparison(results)

    # Print evaluation report
    evaluator.print_evaluation_report(report)

    # Save evaluation report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evaluation_report_{timestamp}.json"
    evaluator.save_evaluation(report, filename)

    return report


def test_baseline_vs_embedding():
    """Compare baseline-only vs baseline+embedding approaches."""
    print("\n" + "="*80)
    print("TEST 4: Baseline vs Baseline+Embedding Comparison")
    print("="*80)

    handler = LLMHandler()

    test_query = "Show me flights with severe delays and poor food ratings."

    print(f"\nQuery: {test_query}")

    # Test with baseline only
    print("\n--- Baseline Only ---")
    result_baseline = handler.generate_answer(test_query, use_embeddings=False)
    print(f"Answer: {result_baseline['answer'][:200]}...")

    # Test with baseline + embeddings
    print("\n--- Baseline + Embeddings ---")
    result_combined = handler.generate_answer(test_query, use_embeddings=True)
    print(f"Answer: {result_combined['answer'][:200]}...")

    # Compare
    print("\n--- Comparison ---")
    print(f"Baseline only - Context length: {len(result_baseline['context'])}")
    print(f"Combined - Context length: {len(result_combined['context'])}")
    print(f"Baseline only - Answer length: {len(result_baseline['answer'])}")
    print(f"Combined - Answer length: {len(result_combined['answer'])}")


def run_all_tests():
    """Run all test scenarios."""
    print("\n" + "#"*80)
    print("# LLM LAYER COMPREHENSIVE TEST SUITE")
    print("#"*80)

    try:
        # Test 1: Single query
        test_single_query()

        # Test 2: Model comparison
        comparator, results = test_model_comparison()

        # Test 3: Evaluation
        test_evaluation(comparator, results)

        # Test 4: Baseline vs Embedding
        test_baseline_vs_embedding()

        print("\n" + "#"*80)
        print("# ALL TESTS COMPLETED SUCCESSFULLY")
        print("#"*80)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


def interactive_mode():
    """Interactive mode for testing queries."""
    print("\n" + "="*80)
    print("INTERACTIVE MODE")
    print("="*80)
    print("Enter your query (or 'quit' to exit)")

    handler = LLMHandler()

    while True:
        query = input("\n> ")

        if query.lower() in ['quit', 'exit', 'q']:
            break

        try:
            result = handler.generate_answer(query)

            print("\n--- Answer ---")
            print(result['answer'])

            # Ask if user wants to see details
            show_details = input("\nShow details? (y/n): ")
            if show_details.lower() == 'y':
                print("\n--- Context ---")
                print(result['context'])

        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test LLM Layer")
    parser.add_argument("--test", choices=["single", "comparison", "all", "interactive"],
                       default="all", help="Which test to run")

    args = parser.parse_args()

    if args.test == "single":
        test_single_query()
    elif args.test == "comparison":
        comparator, results = test_model_comparison()
        test_evaluation(comparator, results)
    elif args.test == "interactive":
        interactive_mode()
    else:
        run_all_tests()