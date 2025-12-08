from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import os 
from dotenv import load_dotenv

load_dotenv()

# We'll test with MiniLM for speed
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

uri = os.getenv('NEO4J_URI', 'neo4j://localhost:7687')
username = os.getenv('NEO4J_USERNAME', 'neo4j')
password = os.getenv('NEO4J_PASSWORD', 'password')
driver = GraphDatabase.driver(uri, auth=(username, password))

def search(query, top_k=3):
    embedding = model.encode(query).tolist()
    
    cypher = """
    CALL db.index.vector.queryNodes('minilm_vec_index', $k, $vec)
    YIELD node, score
    
    # Traverse back from Vector Node to Journey to Passenger
    MATCH (j:Journey)-[:HAS_VECTOR]->(node)
    MATCH (p:Passenger)-[:TOOK]->(j)
    
    RETURN 
        score,
        node.text AS semantic_text,
        j.feedback_ID AS feedback_id,
        j.arrival_delay_minutes AS actual_delay,
        j.food_satisfaction_score AS actual_food
    """
    
    with driver.session() as session:
        result = session.run(cypher, k=top_k, vec=embedding)
        return [dict(r) for r in result]

if __name__ == "__main__":
    print("--- Testing Semantic Search ---")
    q = "severe delay with terrible food"
    print(f"Query: '{q}'")
    
    results = search(q)
    for r in results:
        print(f"\nScore: {r['score']:.4f}")
        print(f"Text: {r['semantic_text']}")
        print(f"DB Check -> Delay: {r['actual_delay']}, Food: {r['actual_food']}")