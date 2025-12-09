# LLM Layer - Graph-RAG System

This module implements **Task 3 (LLM Layer)** of the MS3 Graph-RAG Travel Assistant project.

## Overview

The LLM Layer combines results from:
1. **Baseline retrieval** (structured Cypher queries)
2. **Embedding-based retrieval** (semantic search)

And uses structured prompts to generate grounded, factual answers using LLMs.

## Components

### 1. `llm_handler.py` - Main LLM Handler
**Purpose**: Orchestrates the complete Graph-RAG pipeline

**Key Features**:
- Combines baseline Cypher queries with embedding-based semantic search
- Formats results into structured context
- Creates prompts with **Context**, **Persona**, and **Task** structure
- Supports multiple LLM models
- Removes duplicate results intelligently

**Main Class**: `LLMHandler`

**Methods**:
- `get_baseline_results(query)` - Get Cypher query results
- `get_embedding_results(query)` - Get semantic search results
- `combine_results(baseline, embedding)` - Merge and deduplicate
- `format_context(combined)` - Format for LLM consumption
- `create_structured_prompt(query, context)` - Build prompt with persona/task
- `generate_answer(query, model, temperature)` - Complete pipeline

**Usage**:
```python
from MS3.LLM_layer import LLMHandler

handler = LLMHandler()
result = handler.generate_answer("Which aircraft have highest delays?")
print(result["answer"])
```

---

### 2. `model_comparison.py` - Multi-Model Comparison
**Purpose**: Compare multiple LLM models side-by-side

**Key Features**:
- Tests multiple queries across multiple models
- Measures quantitative metrics (response time, token usage)
- Supports batch processing
- Generates comparison summaries
- Saves results to JSON

**Main Class**: `ModelComparator`

**Supported Models** (via Groq - Free):
- `llama-3.1-8b` - Fast, good quality
- `llama-3.1-70b` - Higher quality, slower
- `mixtral-8x7b` - Mixture of experts
- `gemma-7b` - Google's Gemma

**Usage**:
```python
from MS3.LLM_layer import ModelComparator

comparator = ModelComparator()

queries = [
    "Which aircraft types have the highest delay?",
    "How do Boomers rate the food service?"
]

models = ["llama-3.1-8b", "mixtral-8x7b", "gemma-7b"]

results = comparator.run_batch_comparison(queries, models)
comparator.print_summary()
comparator.save_results("my_comparison.json")
```

---

### 3. `evaluation.py` - Evaluation Framework
**Purpose**: Evaluate LLM responses quantitatively and qualitatively

**Quantitative Metrics**:
- Response time
- Word count / token count
- Context utilization ratio
- Result counts

**Qualitative Metrics**:
- **Relevance**: How well answer matches query
- **Factual Grounding**: Answer uses provided data
- **Completeness**: Answer fully addresses question
- **Clarity**: Clear, well-structured response
- **No Hallucination**: Confidence that answer doesn't make up facts

**Main Class**: `EvaluationMetrics`

**Usage**:
```python
from MS3.LLM_layer import EvaluationMetrics

evaluator = EvaluationMetrics()

# Evaluate single result
result = handler.generate_answer("Show me delays for JNX")
quant_metrics = evaluator.evaluate_quantitative(result)
qual_metrics = evaluator.evaluate_qualitative(result)

# Evaluate comparison
comparison_results = comparator.run_batch_comparison(queries, models)
report = evaluator.evaluate_comparison(comparison_results)
evaluator.print_evaluation_report(report)
```

---

### 4. `test_llm_layer.py` - Test Suite
**Purpose**: Comprehensive testing and validation

**Test Modes**:
1. **Single Query Test** - Test one query through full pipeline
2. **Model Comparison Test** - Compare multiple models
3. **Evaluation Test** - Generate evaluation reports
4. **Baseline vs Embedding** - Compare approaches
5. **Interactive Mode** - Manual testing

**Usage**:
```bash
# Run all tests
python test_llm_layer.py

# Run specific test
python test_llm_layer.py --test single
python test_llm_layer.py --test comparison
python test_llm_layer.py --test interactive

# Interactive mode
python test_llm_layer.py --test interactive
> Which aircraft types have the highest delay?
```

---

## Prompt Structure

The system uses a **3-part structured prompt**:

### 1. PERSONA
```
You are an Airline Flight Insights Assistant working for the airline company.
Your role is to analyze flight data, passenger feedback, and operational metrics
to provide actionable insights for improving airline operations and customer satisfaction.
You speak professionally and focus on data-driven insights.
```

### 2. CONTEXT
```
=== STRUCTURED QUERY RESULTS ===
Intent: analyze_delays
Entities: {'origin': 'JNX'}
Results: [...]

=== SEMANTIC SEARCH RESULTS ===
Match 1 (Score: 0.856)
A severely delayed short-haul flight...
Details: Flight 2411, JNX → EWX, Delay: 125min, Food: 2/5
```

### 3. TASK
```
Answer the following question using ONLY the provided information.
Do not make up information or hallucinate.

Question: [USER QUERY]

Provide a clear, concise answer that:
1. Directly addresses the question
2. References specific data points
3. Provides actionable insights
4. Uses professional tone
```

---

## Architecture

```
User Query
    ↓
┌─────────────────────────────────────┐
│    Input Preprocessing              │
│  - Intent Classification            │
│  - Entity Extraction (NER)          │
└─────────────────────────────────────┘
    ↓                    ↓
[Baseline Path]    [Embedding Path]
    ↓                    ↓
Cypher Queries    Vector Search
    ↓                    ↓
Neo4j Results    Semantic Results
    ↓                    ↓
    └────────┬───────────┘
             ↓
    ┌────────────────────┐
    │  Combine & Merge   │
    │  - Deduplicate     │
    │  - Rank Results    │
    └────────────────────┘
             ↓
    ┌────────────────────┐
    │  Format Context    │
    └────────────────────┘
             ↓
    ┌────────────────────┐
    │  Create Prompt     │
    │  (Context +        │
    │   Persona + Task)  │
    └────────────────────┘
             ↓
    ┌────────────────────┐
    │   LLM Generation   │
    │  (Multiple Models) │
    └────────────────────┘
             ↓
    ┌────────────────────┐
    │   Evaluation       │
    │  (Quant + Qual)    │
    └────────────────────┘
             ↓
      Final Answer
```

---

## Example Workflow

### Complete Example
```python
from MS3.LLM_layer import LLMHandler, ModelComparator, EvaluationMetrics

# 1. Initialize handler
handler = LLMHandler()

# 2. Single query test
result = handler.generate_answer(
    "Which aircraft types have the highest average delay?",
    model="llama-3.1-8b"
)

print("Answer:", result["answer"])
print("Context used:", len(result["context"]), "chars")

# 3. Compare multiple models
comparator = ModelComparator(handler)

queries = [
    "Show me flights with severe delays",
    "How do Boomers rate the food?",
    "Flights from JNX to EWX over 2000 miles"
]

models = ["llama-3.1-8b", "mixtral-8x7b", "gemma-7b"]

comparison_results = comparator.run_batch_comparison(queries, models)

# 4. Evaluate results
evaluator = EvaluationMetrics()
evaluation_report = evaluator.evaluate_comparison(comparison_results)
evaluator.print_evaluation_report(evaluation_report)

# 5. Save everything
comparator.save_results("comparison.json")
evaluator.save_evaluation(evaluation_report, "evaluation.json")
```

---

## Files Generated

The system generates several output files:

1. **`comparison_results_YYYYMMDD_HHMMSS.json`**
   - Full comparison data
   - All queries, all models
   - Response times, answers, metadata

2. **`evaluation_report_YYYYMMDD_HHMMSS.json`**
   - Quantitative metrics
   - Qualitative scores
   - Model rankings

3. **Test logs and summaries**

---

## Requirements

Ensure you have installed:
```bash
pip install sentence-transformers neo4j openai python-dotenv spacy
python -m spacy download en_core_web_sm
```

And configured your `.env`:
```
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
GROQ_API_KEY=your_groq_key
```

---

## MS3 Task 3 Checklist

- [x] **3a. Combine KG results from baseline and embeddings**
  - Implemented in `LLMHandler.combine_results()`
  - Deduplicates by feedback_ID
  - Prioritizes baseline for exact matches

- [x] **3b. Use structured prompt: context, persona, task**
  - Implemented in `LLMHandler.create_structured_prompt()`
  - Clear separation of persona, context, and task

- [x] **3c. Compare at least 3 models**
  - Implemented in `ModelComparator`
  - Supports multiple free models via Groq
  - Default: llama-3.1-8b, mixtral-8x7b, gemma-7b

- [x] **3d. Qualitative and quantitative evaluation**
  - Implemented in `EvaluationMetrics`
  - Quantitative: response time, tokens, context usage
  - Qualitative: relevance, grounding, clarity, no-hallucination

---

## Next Steps

1. **Run comprehensive tests**: `python test_llm_layer.py`
2. **Generate comparison report** with your 10 questions
3. **Document findings** for presentation
4. **Integrate with Streamlit UI** (Task 4)

---

## Support

For issues or questions, refer to:
- MS3 description PDF
- Base retrieval: `../base_retrieve.py`
- Preprocessing: `../preprocessing.py`
- Embedding tests: `../embedding_test/`