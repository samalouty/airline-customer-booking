from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

# 1. Load models
model_minilm = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
model_mpnet = SentenceTransformer("sentence-transformers/paraphrase-mpnet-base-v2")
model_bge_m3 = SentenceTransformer("BAAI/bge-m3")

# 2. Neo4j connection
def load_config(config_file):
    config = {}
    with open(config_file, 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                config[key] = value
    return config

config = load_config('../../config.txt')
uri = config.get('URI', 'neo4j://localhost:7687')
username = config.get('USERNAME', 'neo4j')
password = config.get('PASSWORD', 'password')

driver = GraphDatabase.driver(uri, auth=(username, password))

def vector_search(query, model_name="minilm", top_k=5):
    """Run similarity search in Neo4j"""
    if model_name == "minilm":
        model = model_minilm
        index_name = "journey_minilm_full_index"
    elif model_name == "mpnet":
        model = model_mpnet
        index_name = "journey_mpnet_full_index"
    else:
        model = model_bge_m3
        index_name = "journey_bge_m3_index"

    query_vec = model.encode(query).tolist()

    cypher = f"""
    CALL db.index.vector.queryNodes("{index_name}", $top_k, $query_vec)
    YIELD node, score
    RETURN node.feedback_ID AS journey, node.full_feature_text AS text, score
    """

    with driver.session() as session:
        result = session.run(cypher, top_k=top_k, query_vec=query_vec)
        return [(r["journey"], r["text"], r["score"]) for r in result]

if __name__ == "__main__":
    print("=== Test Airline Embedding Search ===")
    query = input("Enter your test query (e.g., 'Boomers with low food satisfaction'): ")

    print("\n--- MiniLM Top Results ---")
    results_minilm = vector_search(query, model_name="minilm")
    for j, text, score in results_minilm:
        print(f"{j} | score: {score:.4f}\n{text}\n")

    print("\n--- MPNet Top Results ---")
    results_mpnet = vector_search(query, model_name="mpnet")
    for j, text, score in results_mpnet:
        print(f"{j} | score: {score:.4f}\n{text}\n")
    
    print("\n--- BGE-M3 Top Results ---")
    results_bge_m3 = vector_search(query, model_name="bge_m3")
    for j, text, score in results_bge_m3:
        print(f"{j} | score: {score:.4f}\n{text}\n")
    
    print("=== End of Test ===")
