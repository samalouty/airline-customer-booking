# Quick Start Guide - LLM Layer

Get up and running with the LLM Layer in 5 minutes!

## Prerequisites

1. **Neo4j Database** running with your airline data
2. **Environment variables** configured (`.env` file)
3. **Python packages** installed

```bash
pip install sentence-transformers neo4j openai python-dotenv spacy
python -m spacy download en_core_web_sm
```

## Step 1: Test Single Query (30 seconds)

```bash
cd MS3/LLM_layer
python llm_handler.py
```

This will:
- Initialize the handler
- Test the query: "Which aircraft types have the highest average delay?"
- Show the context retrieved from the KG
- Display the final LLM answer

**Expected Output:**
```
Initializing LLM Handler...
Loading embedding model: BAAI/bge-m3
✓ Handler ready

Test Query: Which aircraft types have the highest average delay?
================================================================================

--- CONTEXT ---
=== STRUCTURED QUERY RESULTS ===
Intent: analyze_delays
...

--- ANSWER ---
Based on the data, the B777-200 aircraft has the highest average delay...
```

---

## Step 2: Compare Models (2-3 minutes)

```bash
python test_llm_layer.py --test comparison
```

This will:
- Load 5 test questions
- Test 3 LLM models: llama-3.1-8b, mixtral-8x7b, gemma-7b
- Generate comparison report
- Save results to JSON

**Expected Output:**
```
MODEL COMPARISON SUMMARY
================================================================================
Model                Success    Avg Time    Avg Words
--------------------------------------------------------------------------------
llama-3.1-8b         100.0%     1.23s       145
mixtral-8x7b         100.0%     2.15s       168
gemma-7b             100.0%     1.87s       132
```

---

## Step 3: Run Full Evaluation (5 minutes)

```bash
python test_llm_layer.py --test all
```

This runs all tests:
1. Single query test
2. Model comparison
3. Evaluation metrics
4. Baseline vs Embedding comparison

**Output Files:**
- `comparison_results_YYYYMMDD_HHMMSS.json`
- `evaluation_report_YYYYMMDD_HHMMSS.json`

---

## Step 4: Interactive Testing

```bash
python test_llm_layer.py --test interactive
```

Test your own queries in real-time:
```
INTERACTIVE MODE
================================================================================
Enter your query (or 'quit' to exit)

> Show me flights with big delays and bad food
--- Answer ---
Based on the structured query results, I found 20 flights with severe delays...

Show details? (y/n): y
--- Context ---
...
```

---

## Step 5: Use in Your Code

```python
from MS3.LLM_layer import LLMHandler

# Initialize
handler = LLMHandler()

# Generate answer
result = handler.generate_answer("Your question here")

# Access results
print("Answer:", result["answer"])
print("Baseline results:", result["baseline_results"])
print("Embedding results:", result["embedding_results"])
```

---

## Common Issues & Solutions

### Issue: "Cannot connect to Neo4j"
**Solution:** Check your `.env` file:
```
NEO4J_URI=neo4j://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```

### Issue: "Model not found" or API errors
**Solution:** Check your Groq API key in `.env`:
```
GROQ_API_KEY=your_groq_key
```
Get a free key at: https://console.groq.com/

### Issue: "Vector index not found"
**Solution:** Run the embedding preparation first:
```bash
cd MS3/embedding_test
python prepare_embeddings.py
python create_indices.py
```

### Issue: "spaCy model not found"
**Solution:** Download the model:
```bash
python -m spacy download en_core_web_sm
```

---

## Quick Testing with Jupyter Notebook

Open `llm_layer_demo.ipynb` in Jupyter:

```bash
jupyter notebook llm_layer_demo.ipynb
```

Run all cells to see:
- Live demos
- Model comparisons
- Evaluation metrics
- Interactive examples

---

## What Each File Does

| File | Purpose | Runtime |
|------|---------|---------|
| `llm_handler.py` | Main pipeline | 30s |
| `model_comparison.py` | Compare models | 2-5min |
| `evaluation.py` | Evaluate quality | 1min |
| `test_llm_layer.py` | Full test suite | 5min |
| `llm_layer_demo.ipynb` | Interactive notebook | - |

---

## Next Steps

1. ✅ Test the system with your 10 questions
2. ✅ Generate comparison reports
3. ✅ Document findings for presentation
4. ✅ Proceed to Task 4 (Streamlit UI)

---

## Need Help?

- Check `README.md` for detailed documentation
- Review MS3 description PDF for requirements
- Test with `test_llm_layer.py --test single` first
- Use `--test interactive` to debug specific queries

---

## MS3 Task 3 Completion Checklist

- [x] Combine baseline + embedding results
- [x] Structured prompts (Context, Persona, Task)
- [x] Compare at least 3 models
- [x] Quantitative metrics (time, tokens, etc.)
- [x] Qualitative metrics (relevance, grounding, etc.)
- [x] Save comparison results
- [x] Generate evaluation reports
- [x] Test with 10 questions
- [x] Documentation complete

**Status: READY FOR TASK 4 (UI)** ✅