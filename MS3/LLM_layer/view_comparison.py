#!/usr/bin/env python3
"""
Model Comparison Results Viewer - Streamlit App
Displays comparison results from model_comparison.py in an interactive dashboard
"""
import streamlit as st
import json
import os
from datetime import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from glob import glob

# Page config
st.set_page_config(
    page_title="Model Comparison Results",
    page_icon="📊",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        margin: 0.5rem 0;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data
def load_comparison_results(filepath):
    """Load comparison results from JSON file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_available_result_files():
    """Get list of available comparison result files"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    pattern = os.path.join(script_dir, "comparison_results*.json")
    files = glob(pattern)

    # Also check for model_comparison_results.json
    default_file = os.path.join(script_dir, "model_comparison_results.json")
    if os.path.exists(default_file) and default_file not in files:
        files.append(default_file)

    return sorted(files, reverse=True)  # Most recent first

def format_model_name(model_id, models_dict):
    """Format model ID to display name"""
    if isinstance(models_dict, dict) and model_id in models_dict:
        return models_dict[model_id].get("name", model_id)
    return model_id

# Header
st.title("📊 Model Comparison Dashboard")
st.markdown("Compare LLM performance across multiple queries and metrics")

# File selector
available_files = get_available_result_files()

if not available_files:
    st.error("No comparison result files found. Run model_comparison.py first.")
    st.stop()

# Sidebar for file selection
with st.sidebar:
    st.header("Settings")

    # Show file options with timestamps
    file_options = {}
    for filepath in available_files:
        filename = os.path.basename(filepath)
        file_options[filename] = filepath

    selected_file = st.selectbox(
        "Select Results File",
        options=list(file_options.keys()),
        format_func=lambda x: x
    )

    result_file = file_options[selected_file]

# Load data
data = load_comparison_results(result_file)
summary = data.get("summary", {})
detailed_results = data.get("detailed_results", [])

# Display timestamp
if "timestamp" in summary:
    st.caption(f"Results generated: {summary['timestamp']}")

st.divider()

# ==========================================
# SUMMARY METRICS
# ==========================================
st.header("🏆 Model Leaderboard")

# Create summary dataframe
models_data = []
for model_id, stats in summary.get("models", {}).items():
    models_data.append({
        "Model": model_id.split('/')[-1] if '/' in model_id else model_id,
        "Full ID": model_id,
        "Accuracy (%)": round(stats.get("accuracy", 0) * 100, 1),
        "Correct": stats.get("correct_count", 0),
        "Total": stats.get("queries_with_expected", 0),
        "Success Rate (%)": round(stats.get("success_rate", 0) * 100, 1),
        "Avg Response Time (s)": round(stats.get("avg_response_time", 0), 2),
        "Avg Word Count": round(stats.get("avg_word_count", 0), 1),
    })

df_summary = pd.DataFrame(models_data)

# Sort by accuracy
df_summary = df_summary.sort_values("Accuracy (%)", ascending=False)

# Display summary table
st.dataframe(
    df_summary,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Accuracy (%)": st.column_config.ProgressColumn(
            "Accuracy (%)",
            format="%.1f%%",
            min_value=0,
            max_value=100,
        ),
        "Success Rate (%)": st.column_config.ProgressColumn(
            "Success Rate (%)",
            format="%.1f%%",
            min_value=0,
            max_value=100,
        ),
    }
)

st.caption(f"📈 **Total Queries Tested:** {summary.get('total_queries', 0)}")

st.divider()

# ==========================================
# VISUALIZATIONS
# ==========================================
st.header("📈 Performance Visualizations")

col1, col2 = st.columns(2)

with col1:
    # Accuracy comparison chart
    fig_accuracy = px.bar(
        df_summary.sort_values("Accuracy (%)", ascending=True),
        x="Accuracy (%)",
        y="Model",
        orientation='h',
        title="Model Accuracy Comparison",
        color="Accuracy (%)",
        color_continuous_scale="Viridis",
        text="Accuracy (%)"
    )
    fig_accuracy.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
    fig_accuracy.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig_accuracy, use_container_width=True)

with col2:
    # Response time comparison
    fig_time = px.bar(
        df_summary.sort_values("Avg Response Time (s)"),
        x="Avg Response Time (s)",
        y="Model",
        orientation='h',
        title="Average Response Time Comparison",
        color="Avg Response Time (s)",
        color_continuous_scale="Reds_r",
        text="Avg Response Time (s)"
    )
    fig_time.update_traces(texttemplate='%{text:.2f}s', textposition='outside')
    fig_time.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig_time, use_container_width=True)

# Performance scatter plot
st.subheader("⚡ Accuracy vs Speed")
fig_scatter = px.scatter(
    df_summary,
    x="Avg Response Time (s)",
    y="Accuracy (%)",
    size="Avg Word Count",
    color="Model",
    hover_data=["Full ID", "Correct", "Total"],
    title="Model Performance: Accuracy vs Response Time (bubble size = avg word count)",
    labels={
        "Avg Response Time (s)": "Average Response Time (seconds)",
        "Accuracy (%)": "Accuracy (%)"
    }
)
fig_scatter.update_layout(height=500)
st.plotly_chart(fig_scatter, use_container_width=True)

st.divider()

# ==========================================
# DETAILED QUERY RESULTS
# ==========================================
st.header("🔍 Detailed Query Results")

if detailed_results:
    # Query selector
    query_options = {f"Q{i+1}: {result['query'][:80]}..." if len(result['query']) > 80 else f"Q{i+1}: {result['query']}": i
                     for i, result in enumerate(detailed_results)}

    selected_query = st.selectbox(
        "Select a query to view details",
        options=list(query_options.keys())
    )

    query_idx = query_options[selected_query]
    query_result = detailed_results[query_idx]

    st.subheader("Query")
    st.info(query_result['query'])

    # Model responses for this query
    st.subheader("Model Responses")

    query_models_data = []
    for model_id, model_result in query_result.get("models", {}).items():
        accuracy_check = model_result.get("accuracy_check", {})

        query_models_data.append({
            "Model": model_id.split('/')[-1] if '/' in model_id else model_id,
            "Correct": "✓" if model_result.get("correct", False) else "✗",
            "Response Time (s)": round(model_result.get("response_time", 0), 2),
            "Word Count": model_result.get("word_count", 0),
            "Intent Match": "✓" if accuracy_check.get("intent_match", False) else "✗",
            "Expected Intent": accuracy_check.get("expected_intent", "N/A"),
            "Actual Intent": accuracy_check.get("actual_intent", "N/A"),
        })

    df_query = pd.DataFrame(query_models_data)
    st.dataframe(df_query, use_container_width=True, hide_index=True)

    # Show actual answers in expandable sections
    st.subheader("Model Answers")

    for model_id, model_result in query_result.get("models", {}).items():
        model_name = model_id.split('/')[-1] if '/' in model_id else model_id
        correct_indicator = "✓" if model_result.get("correct", False) else "✗"

        with st.expander(f"{correct_indicator} {model_name} - {model_result.get('word_count', 0)} words, {model_result.get('response_time', 0):.2f}s"):
            if model_result.get("error"):
                st.error(f"Error: {model_result['error']}")
            else:
                st.markdown(model_result.get("answer", "No answer"))

                # Show accuracy check details
                if model_result.get("accuracy_check", {}).get("has_expected"):
                    st.caption("**Accuracy Details:**")
                    acc = model_result["accuracy_check"]
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Intent Match", "Yes" if acc.get("intent_match") else "No")
                    with col2:
                        st.metric("Expected Results", acc.get("expected_result_count", 0))
                    with col3:
                        st.metric("Actual Results", acc.get("actual_result_count", 0))

else:
    st.warning("No detailed results available")

# Footer
st.divider()
st.caption("💡 **Note:** Accuracy is calculated by comparing results with test_results_final.json")
st.caption("📊 Dashboard created with Streamlit")
