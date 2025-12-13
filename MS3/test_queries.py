#!/usr/bin/env python3
"""
Query Test Runner Script
Runs all queries from ten_q.txt, compares expected vs actual Cypher queries,
and saves results to a JSON file.
"""
import os
import sys
import json
import re
from datetime import datetime

# Add the project root to the python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.neo4j_client import driver as default_driver
from MS3.base_retrieve import Neo4jRetriever
from MS3.preprocessing import QueryPreprocessor


def parse_ten_q_file(filepath):
    """
    Parses ten_q.txt and extracts questions with their expected queries.
    Returns a list of dicts: [{question_id, question_text, expected_query}, ...]
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split by question pattern (Q1., Q2., etc.)
    # Pattern matches "Q" followed by number and period
    pattern = r'(Q\d+)\.\s*(.+?)(?=\n\n|\n(?:MATCH|=====)|$)'
    
    questions = []
    
    # Find all questions
    lines = content.split('\n')
    current_question = None
    current_id = None
    current_query_lines = []
    in_query = False
    
    for line in lines:
        # Check if this is a new question
        q_match = re.match(r'^(Q\d+)\.\s*(.+)$', line.strip())
        
        if q_match:
            # Save previous question if exists
            if current_question is not None:
                query_text = '\n'.join(current_query_lines).strip()
                questions.append({
                    'question_id': current_id,
                    'question_text': current_question,
                    'expected_query': query_text
                })
            
            # Start new question
            current_id = q_match.group(1)
            current_question = q_match.group(2).strip()
            current_query_lines = []
            in_query = False
        
        elif current_question is not None:
            # Check if this line starts a Cypher query
            if line.strip().startswith('MATCH') or line.strip().startswith('OPTIONAL'):
                in_query = True
            
            # Skip separator lines
            if line.strip().startswith('====='):
                in_query = False
                continue
            
            # Skip empty lines at the start of query section
            if not in_query and not line.strip():
                continue
            
            # If we're in a query or it's a continuation line
            if in_query or (current_query_lines and line.strip()):
                if line.strip():  # Only add non-empty lines
                    current_query_lines.append(line.strip())
                elif current_query_lines:  # Empty line might end the query
                    # Check if next meaningful content is still part of query
                    pass
    
    # Don't forget the last question
    if current_question is not None:
        query_text = '\n'.join(current_query_lines).strip()
        questions.append({
            'question_id': current_id,
            'question_text': current_question,
            'expected_query': query_text
        })
    
    return questions


def normalize_query(query):
    """
    Normalizes a Cypher query for comparison by:
    - Removing extra whitespace
    - Converting to lowercase
    - Removing parameter placeholders variations
    """
    if not query:
        return ""
    
    # Remove extra whitespace and newlines
    normalized = ' '.join(query.split())
    # Convert to lowercase for comparison
    normalized = normalized.lower()
    # Normalize parameter names ($ variations)
    normalized = re.sub(r'\$\w+', '$param', normalized)
    
    return normalized


def compare_queries(expected, actual):
    """
    Compares two Cypher queries and returns similarity info.
    """
    norm_expected = normalize_query(expected)
    norm_actual = normalize_query(actual)
    
    # Exact match after normalization
    exact_match = norm_expected == norm_actual
    
    # Check if main clauses match
    expected_clauses = set(re.findall(r'\b(match|where|return|order by|limit)\b', norm_expected))
    actual_clauses = set(re.findall(r'\b(match|where|return|order by|limit)\b', norm_actual))
    clauses_match = expected_clauses == actual_clauses
    
    # Check if key patterns are similar
    expected_patterns = set(re.findall(r'\([\w:]+\)', norm_expected))
    actual_patterns = set(re.findall(r'\([\w:]+\)', norm_actual))
    patterns_overlap = len(expected_patterns & actual_patterns) / max(len(expected_patterns), 1)
    
    return {
        'exact_match': exact_match,
        'clauses_match': clauses_match,
        'pattern_similarity': round(patterns_overlap, 2),
        'normalized_expected': norm_expected[:200] + '...' if len(norm_expected) > 200 else norm_expected,
        'normalized_actual': norm_actual[:200] + '...' if len(norm_actual) > 200 else norm_actual
    }


def serialize_results(results):
    """
    Serializes Neo4j results to JSON-compatible format.
    Handles Node and Relationship objects.
    """
    if isinstance(results, str):
        return results  # Error message
    
    if not isinstance(results, list):
        return str(results)
    
    serialized = []
    for record in results:
        if isinstance(record, dict):
            row = {}
            for key, value in record.items():
                if hasattr(value, 'items') and callable(value.items):
                    # Neo4j Node or Relationship
                    row[key] = dict(value.items())
                elif hasattr(value, '__dict__'):
                    row[key] = str(value)
                else:
                    row[key] = value
            serialized.append(row)
        else:
            serialized.append(str(record))
    
    return serialized


def run_all_tests(questions, processor, retriever):
    """
    Runs all test queries and collects results.
    """
    results = []
    
    for i, q in enumerate(questions):
        print(f"\n[{i+1}/{len(questions)}] Testing {q['question_id']}: {q['question_text'][:50]}...")
        
        test_result = {
            'question_id': q['question_id'],
            'question_text': q['question_text'],
            'expected_query': q['expected_query'],
            'actual_query': None,
            'intent': None,
            'entities': None,
            'parameters': None,
            'query_results': None,
            'result_count': 0,
            'comparison': None,
            'success': False,
            'error': None
        }
        
        try:
            # Process the query
            intent, entities, parameters = processor.process_query(q['question_text'])
            
            test_result['intent'] = intent
            test_result['entities'] = entities
            test_result['parameters'] = parameters
            
            if intent == "unknown":
                test_result['error'] = "Unknown intent"
                results.append(test_result)
                continue
            
            # Merge entities and parameters
            combined = {**entities, **parameters}
            
            # Run the query
            query_results, actual_query = retriever.run_query(intent, combined)
            
            test_result['actual_query'] = actual_query
            
            # Serialize results
            serialized_results = serialize_results(query_results)
            test_result['query_results'] = serialized_results
            
            if isinstance(serialized_results, list):
                test_result['result_count'] = len(serialized_results)
            
            # Compare queries
            if q['expected_query'] and actual_query:
                comparison = compare_queries(q['expected_query'], actual_query)
                test_result['comparison'] = comparison
                
                # Determine success: exact match or high similarity
                test_result['success'] = (
                    comparison['exact_match'] or 
                    (comparison['clauses_match'] and comparison['pattern_similarity'] >= 0.7)
                )
            elif actual_query:
                # No expected query to compare, but we got a result
                test_result['success'] = True
                test_result['comparison'] = {'note': 'No expected query provided for comparison'}
            
        except Exception as e:
            test_result['error'] = str(e)
            print(f"  ERROR: {e}")
        
        results.append(test_result)
        
        # Print brief status
        status = "✓" if test_result['success'] else "✗"
        print(f"  {status} Intent: {test_result['intent']}, Results: {test_result['result_count']}")
    
    return results


def generate_summary(results):
    """
    Generates a summary of test results.
    """
    total = len(results)
    successful = sum(1 for r in results if r['success'])
    failed = total - successful
    
    by_intent = {}
    for r in results:
        intent = r['intent'] or 'unknown'
        if intent not in by_intent:
            by_intent[intent] = {'total': 0, 'success': 0}
        by_intent[intent]['total'] += 1
        if r['success']:
            by_intent[intent]['success'] += 1
    
    errors = [r for r in results if r['error']]
    
    return {
        'total_queries': total,
        'successful': successful,
        'failed': failed,
        'success_rate': round(successful / total * 100, 2) if total > 0 else 0,
        'by_intent': by_intent,
        'error_count': len(errors),
        'failed_queries': [
            {'id': r['question_id'], 'text': r['question_text'], 'error': r['error']}
            for r in results if not r['success']
        ]
    }


def main():
    print("=" * 60)
    print("AIRLINE QUERY TEST RUNNER")
    print("=" * 60)
    
    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ten_q_path = os.path.join(script_dir, 'ten_q.txt')
    
    # Output filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_path = os.path.join(script_dir, f'test_results_{timestamp}.json')
    
    # Parse questions
    print(f"\nParsing questions from: {ten_q_path}")
    questions = parse_ten_q_file(ten_q_path)
    print(f"Found {len(questions)} questions")
    
    # Initialize components
    print("\nInitializing retriever and preprocessor...")
    retriever = Neo4jRetriever(default_driver)
    processor = QueryPreprocessor(retriever)
    
    # Run tests
    print("\nRunning tests...")
    print("-" * 60)
    
    results = run_all_tests(questions, processor, retriever)
    
    # Generate summary
    summary = generate_summary(results)
    
    # Compile final output
    output = {
        'timestamp': timestamp,
        'summary': summary,
        'results': results
    }
    
    # Save to JSON
    print("\n" + "=" * 60)
    print("SAVING RESULTS")
    print("=" * 60)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total Queries: {summary['total_queries']}")
    print(f"Successful: {summary['successful']} ({summary['success_rate']}%)")
    print(f"Failed: {summary['failed']}")
    print(f"Errors: {summary['error_count']}")
    
    print("\nResults by Intent:")
    for intent, stats in summary['by_intent'].items():
        rate = round(stats['success'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0
        print(f"  {intent}: {stats['success']}/{stats['total']} ({rate}%)")
    
    if summary['failed_queries']:
        print("\nFailed Queries:")
        for fq in summary['failed_queries'][:10]:  # Show first 10
            print(f"  - {fq['id']}: {fq['text'][:50]}...")
            if fq['error']:
                print(f"    Error: {fq['error']}")
    
    return output


if __name__ == "__main__":
    main()
