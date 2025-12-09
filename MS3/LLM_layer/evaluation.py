#!/usr/bin/env python3
"""
Evaluation Framework for LLM Responses
Includes both quantitative and qualitative metrics
"""
import os
import sys
import json
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class EvaluationMetrics:
    """
    Evaluates LLM responses using quantitative and qualitative measures.

    Quantitative Metrics:
    - Response time
    - Token/word count
    - Cost estimation
    - Context utilization

    Qualitative Metrics:
    - Relevance to query
    - Factual grounding (uses provided data)
    - Completeness
    - Clarity
    - Hallucination detection
    """

    def __init__(self):
        self.evaluations = []

    def evaluate_quantitative(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate quantitative metrics for a single result.

        Args:
            result: Result from LLMHandler.generate_answer()

        Returns:
            Dictionary of quantitative metrics
        """
        answer = result.get("answer", "")
        context = result.get("context", "")

        metrics = {
            "response_time": result.get("response_time", 0),
            "answer_length": len(answer),
            "word_count": len(answer.split()),
            "sentence_count": len([s for s in answer.split('.') if s.strip()]),
            "context_length": len(context),
            "context_words": len(context.split()),
            "baseline_results_count": len(result.get("baseline_results", {}).get("results", [])),
            "embedding_results_count": len(result.get("embedding_results", {}).get("results", [])),
        }

        # Calculate context utilization ratio
        if metrics["context_words"] > 0:
            metrics["context_utilization_ratio"] = metrics["word_count"] / metrics["context_words"]
        else:
            metrics["context_utilization_ratio"] = 0

        return metrics

    def evaluate_qualitative(self, result: Dict[str, Any],
                            ground_truth: str = None) -> Dict[str, Any]:
        """
        Evaluate qualitative aspects of the answer.

        Args:
            result: Result from LLMHandler.generate_answer()
            ground_truth: Optional expected answer for comparison

        Returns:
            Dictionary of qualitative metrics
        """
        answer = result.get("answer", "")
        context = result.get("context", "")
        query = result.get("query", "")

        scores = {
            "relevance": self._score_relevance(answer, query),
            "factual_grounding": self._score_grounding(answer, context),
            "completeness": self._score_completeness(answer, query),
            "clarity": self._score_clarity(answer),
            "no_hallucination": self._detect_no_hallucination(answer, context),
        }

        # Overall qualitative score (average)
        scores["overall_qualitative"] = sum(scores.values()) / len(scores)

        # Add human-readable assessment
        scores["assessment"] = self._generate_assessment(scores)

        return scores

    def _score_relevance(self, answer: str, query: str) -> float:
        """
        Score how relevant the answer is to the query (0-1).

        Simple heuristic: Check for query keywords in answer.
        """
        if not answer or not query:
            return 0.0

        # Extract key terms from query (nouns, numbers, important words)
        query_lower = query.lower()
        answer_lower = answer.lower()

        # Common airline terms to look for
        keywords = []

        # Extract important words (simple approach)
        for word in query_lower.split():
            if len(word) > 3 and word not in ['what', 'which', 'show', 'find', 'list', 'give']:
                keywords.append(word)

        if not keywords:
            return 0.5  # Neutral if no keywords

        # Count how many keywords appear in answer
        matches = sum(1 for kw in keywords if kw in answer_lower)
        return min(matches / len(keywords), 1.0)

    def _score_grounding(self, answer: str, context: str) -> float:
        """
        Score how well the answer is grounded in the provided context (0-1).

        Checks if numbers and specific facts in answer appear in context.
        """
        if not answer or not context:
            return 0.0

        # Extract numbers from answer
        answer_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\b', answer))

        if not answer_numbers:
            # If no numbers, check for specific entities
            return 0.7  # Moderate score

        # Check how many numbers from answer appear in context
        context_numbers = set(re.findall(r'\b\d+(?:\.\d+)?\b', context))

        if not context_numbers:
            return 0.3  # Low score if answer has numbers but context doesn't

        grounded_numbers = answer_numbers.intersection(context_numbers)
        grounding_ratio = len(grounded_numbers) / len(answer_numbers)

        return grounding_ratio

    def _score_completeness(self, answer: str, query: str) -> float:
        """
        Score how complete the answer is (0-1).

        Heuristic: Longer answers are more complete, but not too long.
        """
        if not answer:
            return 0.0

        word_count = len(answer.split())

        # Optimal range: 30-150 words
        if word_count < 10:
            return 0.3  # Too short
        elif word_count < 30:
            return 0.6  # Brief but acceptable
        elif word_count <= 150:
            return 1.0  # Good length
        elif word_count <= 250:
            return 0.8  # A bit long but okay
        else:
            return 0.6  # Too verbose

    def _score_clarity(self, answer: str) -> float:
        """
        Score the clarity of the answer (0-1).

        Checks for:
        - Proper sentence structure
        - Not too many technical jargon
        - Clear language
        """
        if not answer:
            return 0.0

        score = 1.0

        # Check for incomplete sentences
        sentences = [s.strip() for s in answer.split('.') if s.strip()]
        if len(sentences) == 0:
            return 0.2

        # Penalize very short sentences (likely incomplete)
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
        if avg_sentence_length < 5:
            score -= 0.3

        # Check for error messages in answer
        error_keywords = ['error', 'cannot', 'unable', 'not found', 'no data']
        if any(kw in answer.lower() for kw in error_keywords):
            score -= 0.2

        return max(score, 0.0)

    def _detect_no_hallucination(self, answer: str, context: str) -> float:
        """
        Score confidence that answer does not hallucinate (0-1).

        1.0 = High confidence no hallucination
        0.0 = Likely hallucination
        """
        if not answer:
            return 1.0  # No answer = no hallucination

        # Check for hedge phrases (good signs)
        hedge_phrases = [
            'based on the data',
            'according to',
            'the results show',
            'from the context',
            'data indicates',
            'cannot determine',
            'not available',
            'no information'
        ]

        has_hedging = any(phrase in answer.lower() for phrase in hedge_phrases)

        # Check for absolute claims without data
        absolute_claims = ['always', 'never', 'all', 'none', 'every', 'must']
        has_absolutes = any(claim in answer.lower() for claim in absolute_claims)

        score = 0.7  # Base score

        if has_hedging:
            score += 0.2  # Good: references data

        if has_absolutes:
            score -= 0.3  # Bad: makes absolute claims

        # Check if answer says "I don't know" when no context
        if not context or len(context) < 50:
            if any(phrase in answer.lower() for phrase in ['no data', 'cannot', 'not available']):
                score = 1.0  # Correctly admits lack of data

        return max(min(score, 1.0), 0.0)

    def _generate_assessment(self, scores: Dict[str, float]) -> str:
        """
        Generate human-readable assessment from scores.

        Args:
            scores: Dictionary of metric scores

        Returns:
            Assessment string
        """
        overall = scores["overall_qualitative"]

        if overall >= 0.8:
            return "Excellent"
        elif overall >= 0.6:
            return "Good"
        elif overall >= 0.4:
            return "Fair"
        else:
            return "Poor"

    def evaluate_comparison(self, comparison_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Evaluate a full model comparison.

        Args:
            comparison_results: Results from ModelComparator.run_batch_comparison()

        Returns:
            Comprehensive evaluation report
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_queries": len(comparison_results),
            "models": {}
        }

        # Collect all model keys
        all_models = set()
        for result in comparison_results:
            all_models.update(result["models"].keys())

        # Evaluate each model
        for model_key in all_models:
            model_scores = {
                "quantitative": [],
                "qualitative": []
            }

            for query_result in comparison_results:
                if model_key in query_result["models"]:
                    model_data = query_result["models"][model_key]

                    if model_data.get("answer"):
                        # Create result dict for evaluation
                        eval_result = {
                            "answer": model_data["answer"],
                            "context": "",  # Would need to store this
                            "query": query_result["query"],
                            "response_time": model_data.get("response_time", 0)
                        }

                        # Quantitative metrics
                        quant = self.evaluate_quantitative(eval_result)
                        model_scores["quantitative"].append(quant)

                        # Qualitative metrics
                        qual = self.evaluate_qualitative(eval_result)
                        model_scores["qualitative"].append(qual)

            # Aggregate scores
            if model_scores["quantitative"]:
                report["models"][model_key] = {
                    "avg_response_time": sum(q["response_time"] for q in model_scores["quantitative"]) / len(model_scores["quantitative"]),
                    "avg_word_count": sum(q["word_count"] for q in model_scores["quantitative"]) / len(model_scores["quantitative"]),
                    "avg_relevance": sum(q["relevance"] for q in model_scores["qualitative"]) / len(model_scores["qualitative"]),
                    "avg_grounding": sum(q["factual_grounding"] for q in model_scores["qualitative"]) / len(model_scores["qualitative"]),
                    "avg_clarity": sum(q["clarity"] for q in model_scores["qualitative"]) / len(model_scores["qualitative"]),
                    "avg_no_hallucination": sum(q["no_hallucination"] for q in model_scores["qualitative"]) / len(model_scores["qualitative"]),
                    "overall_quality": sum(q["overall_qualitative"] for q in model_scores["qualitative"]) / len(model_scores["qualitative"])
                }

        return report

    def save_evaluation(self, report: Dict[str, Any], filename: str = "evaluation_report.json"):
        """
        Save evaluation report to file.

        Args:
            report: Evaluation report dictionary
            filename: Output filename
        """
        filepath = os.path.join(os.path.dirname(__file__), filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\nEvaluation report saved to: {filepath}")

    def print_evaluation_report(self, report: Dict[str, Any]):
        """
        Print formatted evaluation report.

        Args:
            report: Evaluation report from evaluate_comparison()
        """
        print("\n" + "="*80)
        print("EVALUATION REPORT")
        print("="*80)

        print(f"\nTotal Queries Evaluated: {report['total_queries']}")
        print("\nModel Rankings:")
        print("-"*80)
        print(f"{'Model':<20} {'Quality':<10} {'Relevance':<12} {'Grounding':<12} {'Clarity':<10}")
        print("-"*80)

        # Sort models by overall quality
        sorted_models = sorted(
            report["models"].items(),
            key=lambda x: x[1].get("overall_quality", 0),
            reverse=True
        )

        for model_key, metrics in sorted_models:
            print(f"{model_key:<20} "
                  f"{metrics.get('overall_quality', 0)*100:>6.1f}%   "
                  f"{metrics.get('avg_relevance', 0)*100:>8.1f}%    "
                  f"{metrics.get('avg_grounding', 0)*100:>8.1f}%    "
                  f"{metrics.get('avg_clarity', 0)*100:>6.1f}%")

        print("-"*80)
        print("\nPerformance Metrics:")
        print("-"*80)
        print(f"{'Model':<20} {'Avg Time':<12} {'Avg Words':<12} {'No Halluc.':<12}")
        print("-"*80)

        for model_key, metrics in sorted_models:
            print(f"{model_key:<20} "
                  f"{metrics.get('avg_response_time', 0):>8.2f}s    "
                  f"{metrics.get('avg_word_count', 0):>8.1f}    "
                  f"{metrics.get('avg_no_hallucination', 0)*100:>8.1f}%")

        print("-"*80)


# Test the evaluation framework
if __name__ == "__main__":
    print("Evaluation Framework Test")

    evaluator = EvaluationMetrics()

    # Sample result
    sample_result = {
        "query": "Which aircraft types have the highest average delay?",
        "answer": "Based on the data, the B777-200 has the highest average delay of 45 minutes, followed by the A320-200 with 32 minutes average delay.",
        "context": "Aircraft: B777-200, Average Delay: 45.2 minutes\nAircraft: A320-200, Average Delay: 32.1 minutes",
        "response_time": 1.5
    }

    # Quantitative evaluation
    quant = evaluator.evaluate_quantitative(sample_result)
    print("\nQuantitative Metrics:")
    for key, value in quant.items():
        print(f"  {key}: {value}")

    # Qualitative evaluation
    qual = evaluator.evaluate_qualitative(sample_result)
    print("\nQualitative Metrics:")
    for key, value in qual.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")