"""
Configuration file for embedding models and LLMs
Makes it easy to add new models in the future
"""

# ==========================================
# EMBEDDING MODELS CONFIGURATION
# ==========================================
EMBEDDING_MODELS = {
    "BAAI/bge-m3": {
        "name": "BGE-M3 (1024-dim)",
        "dimensions": 1024,
        "index": "bgem3_vec_index",
        "description": "Best overall performance, highest dimensional space",
        "model_source": "HuggingFace",
        "recommended_use": "Production - High accuracy"
    },
    "sentence-transformers/paraphrase-mpnet-base-v2": {
        "name": "MPNet (768-dim)",
        "dimensions": 768,
        "index": "mpnet_vec_index",
        "description": "Balanced performance and speed",
        "model_source": "HuggingFace",
        "recommended_use": "Development - Balanced"
    },
    "sentence-transformers/all-MiniLM-L6-v2": {
        "name": "MiniLM (384-dim)",
        "dimensions": 384,
        "index": "minilm_vec_index",
        "description": "Fastest, lower dimensions",
        "model_source": "HuggingFace",
        "recommended_use": "Testing - Fast inference"
    }
}

# ==========================================
# LLM MODELS CONFIGURATION
# ==========================================
# These are currently using Groq API (free tier)
# To add new models: Add entry here and ensure the model is available via your API
LLM_MODELS = {
    "llama-3.1-8b-instant": {
        "name": "Llama 3.1 8B (Fast)",
        "description": "Fast inference, good for quick responses",
        "provider": "Groq",
        "context_length": 8192,
        "recommended_temp": 0.1,
        "cost": "Free",
        "use_case": "Production - Fast responses"
    },
    "llama-3.1-70b-versatile": {
        "name": "Llama 3.1 70B (Powerful)",
        "description": "Higher quality answers, slower inference",
        "provider": "Groq",
        "context_length": 8192,
        "recommended_temp": 0.1,
        "cost": "Free",
        "use_case": "Production - High accuracy"
    },
    "mixtral-8x7b-32768": {
        "name": "Mixtral 8x7B",
        "description": "Mixture of Experts, balanced performance",
        "provider": "Groq",
        "context_length": 32768,
        "recommended_temp": 0.1,
        "cost": "Free",
        "use_case": "Long context queries"
    },
    "gemma2-9b-it": {
        "name": "Gemma 2 9B",
        "description": "Google's model, good reasoning",
        "provider": "Groq",
        "context_length": 8192,
        "recommended_temp": 0.1,
        "cost": "Free",
        "use_case": "Reasoning tasks"
    }
}

# ==========================================
# RETRIEVAL METHODS CONFIGURATION
# ==========================================
RETRIEVAL_METHODS = {
    "baseline": {
        "label": "Baseline (Cypher Queries)",
        "description": "Rule-based retrieval using Cypher queries with intent classification and entity extraction",
        "uses_embeddings": False,
        "uses_cypher": True,
        "advantages": [
            "Precise pattern matching",
            "Deterministic results",
            "Explainable queries"
        ]
    },
    "embedding": {
        "label": "Embedding (Semantic Search)",
        "description": "Semantic similarity search using vector embeddings",
        "uses_embeddings": True,
        "uses_cypher": False,
        "advantages": [
            "Handles semantic similarity",
            "Works with natural language",
            "Finds related concepts"
        ]
    },
    "hybrid": {
        "label": "Hybrid (Combined)",
        "description": "Combines both Cypher and embedding-based retrieval for comprehensive results",
        "uses_embeddings": True,
        "uses_cypher": True,
        "advantages": [
            "Best of both worlds",
            "Maximum coverage",
            "Robust to query variations"
        ]
    }
}

# ==========================================
# UI CONFIGURATION
# ==========================================
UI_CONFIG = {
    "app_title": "Airline Flight Insights Assistant",
    "app_icon": "✈️",
    "theme": {
        "primary_color": "#667eea",
        "secondary_color": "#764ba2",
        "background_gradient": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        "font_family": "Inter"
    },
    "default_settings": {
        "retrieval_method": "hybrid",
        "embedding_model": "BAAI/bge-m3",
        "llm_model": "llama-3.1-8b-instant",
        "temperature": 0.1,
        "top_k": 5,
        "show_debug": True
    }
}

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_embedding_model_info(model_key: str) -> dict:
    """Get information about a specific embedding model"""
    return EMBEDDING_MODELS.get(model_key, {})


def get_llm_model_info(model_key: str) -> dict:
    """Get information about a specific LLM model"""
    return LLM_MODELS.get(model_key, {})


def get_retrieval_method_info(method_key: str) -> dict:
    """Get information about a specific retrieval method"""
    return RETRIEVAL_METHODS.get(method_key, {})


def list_available_embedding_models() -> list:
    """List all available embedding models"""
    return list(EMBEDDING_MODELS.keys())


def list_available_llm_models() -> list:
    """List all available LLM models"""
    return list(LLM_MODELS.keys())


def list_available_retrieval_methods() -> list:
    """List all available retrieval methods"""
    return list(RETRIEVAL_METHODS.keys())


# ==========================================
# HOW TO ADD NEW MODELS
# ==========================================
"""
TO ADD A NEW EMBEDDING MODEL:
1. Add entry to EMBEDDING_MODELS dictionary above
2. Ensure the model is available in sentence-transformers
3. Create the corresponding vector index in Neo4j using MS3/embedding_test/create_indices.py
4. Generate embeddings using MS3/embedding_test/prepare_embeddings.py

Example:
    "new-model-name": {
        "name": "Display Name",
        "dimensions": 512,
        "index": "new_model_vec_index",
        "description": "Model description",
        "model_source": "HuggingFace",
        "recommended_use": "When to use this model"
    }

TO ADD A NEW LLM MODEL:
1. Add entry to LLM_MODELS dictionary above
2. Ensure the model is available via your API (Groq, OpenAI, etc.)
3. Update config/openai_client.py if using a different API

Example:
    "model-id": {
        "name": "Display Name",
        "description": "Model description",
        "provider": "API Provider",
        "context_length": 8192,
        "recommended_temp": 0.1,
        "cost": "Pricing info",
        "use_case": "Best use case"
    }
"""
