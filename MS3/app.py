#!/usr/bin/env python3
"""
Airline Flight Insights Assistant - Streamlit UI
Implements Graph-RAG system with multiple retrieval methods and LLM models
"""

import streamlit as st
import sys
import os
import json
from typing import Dict, Any
import plotly.graph_objects as go
import networkx as nx

# Force CPU usage for all models to avoid CUDA OOM errors
os.environ['CUDA_VISIBLE_DEVICES'] = ''

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.neo4j_client import driver as default_driver
from MS3.LLM_layer.llm_handler import LLMHandler
from MS3.base_retrieve import Neo4jRetriever
from sentence_transformers import SentenceTransformer

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Flight Insights AI",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# CUSTOM CSS
# ==========================================
def load_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning(f"Could not load styles from {file_name}")

# Load the external CSS file
css_path = os.path.join(os.path.dirname(__file__), 'styles.css')
load_css(css_path)

# ==========================================
# SESSION STATE INITIALIZATION
# ==========================================
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if 'llm_handler' not in st.session_state:
    st.session_state.llm_handler = None

# ==========================================
# EMBEDDING MODELS CONFIGURATION
# ==========================================
EMBEDDING_MODELS = {
    "BAAI/bge-m3": {
        "name": "BGE-M3 (1024-dim)",
        "dimensions": 1024,
        "index": "bgem3_vec_index",
        "description": "Best overall performance, highest dimensional space"
    },
    "sentence-transformers/paraphrase-mpnet-base-v2": {
        "name": "MPNet (768-dim)",
        "dimensions": 768,
        "index": "mpnet_vec_index",
        "description": "Balanced performance and speed"
    },
    "sentence-transformers/all-MiniLM-L6-v2": {
        "name": "MiniLM (384-dim)",
        "dimensions": 384,
        "index": "minilm_vec_index",
        "description": "Fastest, lower dimensions"
    }
}

# ==========================================
# LLM MODELS CONFIGURATION
# ==========================================
LLM_MODELS = {
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
    "meta-llama/llama-4-maverick-17b-128e-instruct": {
        "name": "Llama 4 Maverick",
        "description": "Advanced Vision capabilities"
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
    }
}

# ==========================================
# HELPER FUNCTIONS
# ==========================================

def initialize_llm_handler(embedding_model: str):
    """Initialize or update LLM handler with selected embedding model"""
    if st.session_state.llm_handler is None or st.session_state.get('current_embedding_model') != embedding_model:
        with st.status(f"🔄 Initializing System with {EMBEDDING_MODELS[embedding_model]['name']}...", expanded=True) as status:
            st.write("Loading embedding models...")
            st.session_state.llm_handler = LLMHandler(embedding_model=embedding_model)
            st.session_state.current_embedding_model = embedding_model
            status.update(label="✅ System Initialized", state="complete", expanded=False)

def create_graph_visualization(results_data: Dict) -> go.Figure:
    """Create a network graph visualization of the retrieved data"""
    G = nx.Graph()
    
    # Extract nodes and edges from results
    baseline_results = results_data.get('baseline_results', {}).get('results', []) or []
    if not isinstance(baseline_results, list):
        baseline_results = []
        
    embedding_results = results_data.get('embedding_results', {}).get('results', []) or []
    if not isinstance(embedding_results, list):
        embedding_results = []
    
    # Combine for visualization
    all_results = baseline_results + embedding_results
    
    if not all_results:
        return None
    
    # Build graph
    node_colors = []
    node_labels = []
    node_sizes = []
    
    for i, result in enumerate(all_results[:15]):  # Limit nodes
        if 'flight_number' in result:
            flight_id = f"F_{result['flight_number']}"
            if flight_id not in G:
                G.add_node(flight_id, node_type='flight', label=f"Flight {result['flight_number']}")
                node_colors.append('#818cf8') # Light Indigo
                node_labels.append(f"SA {result['flight_number']}")
                node_sizes.append(25)

        if 'origin' in result and 'destination' in result:
            origin_id = f"A_{result['origin']}"
            dest_id = f"A_{result['destination']}"
            
            if origin_id not in G:
                G.add_node(origin_id, node_type='airport', label=result['origin'])
                node_colors.append('#34d399') # Emerald 400
                node_labels.append(result['origin'])
                node_sizes.append(35)
            
            if dest_id not in G:
                G.add_node(dest_id, node_type='airport', label=result['destination'])
                node_colors.append('#34d399') # Emerald 400
                node_labels.append(result['destination'])
                node_sizes.append(35)
            
            if 'flight_number' in result:
                flight_id = f"F_{result['flight_number']}"
                G.add_edge(origin_id, flight_id, relation='departs_from')
                G.add_edge(flight_id, dest_id, relation='arrives_at')
    
    if len(G.nodes()) == 0:
        return None
    
    pos = nx.spring_layout(G, k=0.5, iterations=50)
    
    edge_trace = go.Scatter(
        x=[], y=[],
        line=dict(width=1, color='#94a3b8'),
        hoverinfo='none',
        mode='lines'
    )
    
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_trace['x'] += tuple([x0, x1, None])
        edge_trace['y'] += tuple([y0, y1, None])
    
    node_trace = go.Scatter(
        x=[], y=[],
        mode='markers+text',
        hoverinfo='text',
        marker=dict(
            showscale=False,
            color=node_colors,
            size=node_sizes,
            line=dict(width=2, color='#1e293b')
        ),
        text=node_labels,
        textposition="top center",
        textfont=dict(size=11, color='#e2e8f0', family='Inter', weight='bold')
    )
    
    for node in G.nodes():
        x, y = pos[node]
        node_trace['x'] += tuple([x])
        node_trace['y'] += tuple([y])
    
    fig = go.Figure(data=[edge_trace, node_trace],
                   layout=go.Layout(
                       showlegend=False,
                       hovermode='closest',
                       margin=dict(b=0, l=0, r=0, t=0),
                       plot_bgcolor='rgba(0,0,0,0)',
                       paper_bgcolor='rgba(0,0,0,0)',
                       xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                       yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                       height=350,
                       template="plotly_dark"
                   ))
    return fig

def display_cypher_query(intent: str, entities: Dict, executed_query: str = None):
    """Display the actual Cypher query that was executed"""
    if executed_query:
        st.code(executed_query, language='cypher')
        st.caption("Query Parameters")
        st.json(entities)
        return

    retriever = Neo4jRetriever()
    query = retriever.get_query_for_intent(intent, entities)
    
    if query:
        st.code(query, language='cypher')
        st.caption("Query Parameters")
        st.json(entities)
    else:
        st.warning("No query available for this intent")

def format_results_table(results):
    """Format results as a nice table"""
    if not results or not isinstance(results, list):
        return None
    import pandas as pd
    try:
        df = pd.DataFrame(results)
        return df
    except:
        return None

# ==========================================
# SIDEBAR CONFIGURATION
# ==========================================
with st.sidebar:
    st.image("https://img.icons8.com/clouds/200/airplane-take-off.png", width=100)
    
    st.markdown("### Retrieval Strategy")
    retrieval_method = st.radio(
        "Method",
        ["Baseline (Cypher Queries)", "Embedding (Semantic Search)", "Hybrid (Combined)"],
        captions=["Exact graph matches", "Vector similarity search", "Best of both worlds"],
        label_visibility="collapsed"
    )
    
    st.divider()
    
    embedding_model = "BAAI/bge-m3" # Default
    if retrieval_method in ["Embedding (Semantic Search)", "Hybrid (Combined)"]:
        st.markdown("### Embedding Model")
        embedding_model_key = st.selectbox(
            "Select Model",
            list(EMBEDDING_MODELS.keys()),
            format_func=lambda x: EMBEDDING_MODELS[x]["name"],
            label_visibility="collapsed"
        )
        
        model_info = EMBEDDING_MODELS[embedding_model_key]
        st.caption(f"**{model_info['description']}**")
        st.caption(f"Dimensions: {model_info['dimensions']}")
        
        embedding_model = embedding_model_key
    
    st.divider()
    
    st.markdown("### Intelligence")
    llm_model_key = st.selectbox(
        "Language Model",
        list(LLM_MODELS.keys()),
        format_func=lambda x: LLM_MODELS[x]["name"],
        label_visibility="collapsed"
    )
    st.caption(LLM_MODELS[llm_model_key]["description"])
    
    with st.expander("⚙️ Advanced Parameters"):
        temperature = st.slider("Creativity", 0.0, 1.0, 0.1)
        top_k = st.slider("Context Window", 1, 10, 5)
        show_debug = st.toggle("Debug Mode", value=True)

    st.divider()
    if st.button("Clear Conversation", type="secondary", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

# ==========================================
# MAIN UI
# ==========================================

# Header
col1, col2 = st.columns([1, 8])
with col1:
    st.markdown("<div style='font-size: 3.5rem; text-align: center; margin-top: -10px;'>✈️</div>", unsafe_allow_html=True)
with col2:
    st.title("Flight Insights AI")
    st.markdown("##### <span style='color: #94a3b8'>Nextest-Gen Airline Operations Assistant</span>", unsafe_allow_html=True)

st.markdown("<div style='margin-bottom: 2rem'></div>", unsafe_allow_html=True)

# Welcome message if empty history
if not st.session_state.chat_history:
    st.markdown("""
        <h3 style='text-align: center; margin-bottom: 2rem; color: #f8fafc'>How can I assist you today?</h3>
    """, unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        <div class="glass-card">
            <div class="card-title">
                <span style="color: #6366f1">📊</span> Delays & Operations
            </div>
            <div class="card-content">
                "Which aircraft types have the highest average delay?"<br>
                "Why are flights from LAX delayed today?"
            </div>
        </div>
        <div style="height: 1rem"></div>
        <div class="glass-card">
            <div class="card-title">
                <span style="color: #e879f9">�</span> Network Analysis
            </div>
            <div class="card-content">
                "Show me all flights from JFK to London"<br>
                "List all distinct routes from Miami."
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    with c2:
        st.markdown("""
        <div class="glass-card">
            <div class="card-title">
                <span style="color: #34d399">�</span> Passenger Experience
            </div>
            <div class="card-content">
                "How do Millennials rate food on Boeing 777 flights?"<br>
                "What is the average satisfaction score for Business Class?"
            </div>
        </div>
        <div style="height: 1rem"></div>
        <div class="glass-card">
            <div class="card-title">
                <span style="color: #60a5fa">🤖</span> System Status
            </div>
            <div class="card-content">
                Connected to Neo4j Knowledge Graph.<br>
                Ready for Hybrid Retrieval (RAG).
            </div>
        </div>
        """, unsafe_allow_html=True)

# Display Chat History
for message in st.session_state.chat_history:
    with st.chat_message("user"):
        st.write(message["query"])
    
    with st.chat_message("assistant"):
        st.markdown(message["result"]["answer"])
        
        # Helper to render the tabs/details for a past message
        result = message["result"]
        with st.expander("🔎 View Analysis & Evidence"):
            tab1, tab2, tab3, tab4 = st.tabs(["📚 Context", "📊 Data", "🗺️ Graph", "🔧 Queries"])
            
            with tab1:
                if result['baseline_results'].get('results'):
                    st.dataframe(format_results_table(result['baseline_results']['results']), use_container_width=True)
                
                if result.get('embedding_results', {}).get('results'):
                    st.write("Semantic Matches:")
                    for item in result['embedding_results']['results'][:3]:
                        st.info(f"score: {item.get('score', 0):.2f} | {item.get('semantic_text')}")

            with tab2:
                 # Data Analysis
                intent = result['baseline_results'].get('intent', 'unknown')
                entities = result['baseline_results'].get('entities', {})
                st.write(f"**Intent:** `{intent}`")
                st.write(f"**Entities:** `{entities}`")

            with tab3:
                # Graph
                fig = create_graph_visualization(result)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.write("No graph visualization available.")

            with tab4:
                # Queries
                baseline = result.get('baseline_results', {})
                intent = baseline.get('intent')
                entities = baseline.get('entities', {})
                executed_query = baseline.get('generated_cypher')

                if executed_query or (intent and intent != 'unknown'):
                    display_cypher_query(intent, entities, executed_query)

# Chat Input
if prompt := st.chat_input("Ask a question about flights, delays, or passengers..."):
    with st.chat_message("user"):
        st.write(prompt)

    # Initialize handler
    if retrieval_method in ["Embedding (Semantic Search)", "Hybrid (Combined)"]:
        initialize_llm_handler(embedding_model)
    else:
        if st.session_state.llm_handler is None:
            initialize_llm_handler("BAAI/bge-m3")

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            handler = st.session_state.llm_handler
            
            # Logic to get result
            if retrieval_method == "Baseline (Cypher Queries)":
                result = handler.generate_answer(
                    prompt, 
                    model=llm_model_key, 
                    temperature=temperature,
                    use_embeddings=False
                )
            elif retrieval_method == "Embedding (Semantic Search)":
                # Embedding logic: This part mirrors the original "Embedding" Logic block
                baseline_results = {"method": "baseline_cypher", "results": [], "intent": "none", "entities": {}}
                embedding_results = handler.get_embedding_results(prompt, top_k=top_k)
                combined = handler.combine_results(baseline_results, embedding_results)
                context = handler.format_context(combined)
                prompt_text = handler.create_structured_prompt(prompt, context)
                from config.openai_client import get_answer
                answer = get_answer(prompt_text, model=llm_model_key, temperature=temperature)
                
                result = {
                    "query": prompt,
                    "baseline_results": baseline_results,
                    "embedding_results": embedding_results,
                    "combined_results": combined,
                    "context": context,
                    "prompt": prompt_text,
                    "answer": answer,
                    "model": llm_model_key
                }
            else: # Hybrid
                result = handler.generate_answer(
                    prompt, 
                    model=llm_model_key, 
                    temperature=temperature,
                    use_embeddings=True
                )
            
            # Show Answer immediately
            st.markdown(result['answer'])
            
            # Show Details immediately for the current turn
            with st.expander("🔎 View Analysis & Evidence", expanded=False):
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["📚 Context", "📊 Data", "🗺️ Graph", "🔧 Queries", "🐛 Debug"])
                
                with tab1:
                    st.caption("Retrieved data used to generate the answer")
                    if result['baseline_results'].get('results'):
                        st.dataframe(format_results_table(result['baseline_results']['results']), use_container_width=True)
                    else:
                        st.info("No direct database matches.")
                        
                    if result.get('embedding_results', {}).get('results'):
                        st.write("Context from vector search:")
                        for item in result['embedding_results']['results'][:3]:
                            with st.container():
                                st.markdown(f"**Score: {item.get('score', 0):.2f}**")
                                st.caption(item.get('semantic_text'))
                                st.divider()

                with tab2:
                    intent = result['baseline_results'].get('intent')
                    st.metric("Detected Intent", intent)
                    if result['baseline_results'].get('entities'):
                        st.write("Extracted Entities:")
                        st.json(result['baseline_results']['entities'])

                with tab3:
                    fig = create_graph_visualization(result)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.write("No graph data to visualize.")

                with tab4:
                    baseline_res = result['baseline_results']
                    executed_query = baseline_res.get('generated_cypher')
                    
                    if executed_query or (intent and intent != "unknown"):
                        display_cypher_query(intent, baseline_res.get('entities', {}), executed_query)
                    else:
                        st.write("No Cypher query generated.")

                with tab5:
                    if show_debug:
                        st.json(result)

    # Save to history
    st.session_state.chat_history.append({
        "query": prompt,
        "result": result,
        "retrieval_method": retrieval_method,
        "embedding_model": embedding_model,
        "llm_model": llm_model_key
    })
