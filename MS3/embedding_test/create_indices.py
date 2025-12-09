from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

uri = os.getenv('NEO4J_URI', 'neo4j://localhost:7687')
username = os.getenv('NEO4J_USERNAME', 'neo4j')
password = os.getenv('NEO4J_PASSWORD', 'password')

driver = GraphDatabase.driver(uri, auth=(username, password))

def create_indices():
    with driver.session() as session:
        print("Creating indices on :JourneyVector...")

        # 1. MiniLM
        session.run("""
            CREATE VECTOR INDEX minilm_vec_index IF NOT EXISTS
            FOR (n:JourneyVector) ON (n.minilm_embedding)
            OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}
        """)
        
        # 2. MPNet
        session.run("""
            CREATE VECTOR INDEX mpnet_vec_index IF NOT EXISTS
            FOR (n:JourneyVector) ON (n.mpnet_embedding)
            OPTIONS {indexConfig: {`vector.dimensions`: 768, `vector.similarity_function`: 'cosine'}}
        """)

        # 3. BGE-M3
        session.run("""
            CREATE VECTOR INDEX bgem3_vec_index IF NOT EXISTS
            FOR (n:JourneyVector) ON (n.bgem3_embedding)
            OPTIONS {indexConfig: {`vector.dimensions`: 1024, `vector.similarity_function`: 'cosine'}}
        """)

        print("Indices created successfully.")

if __name__ == "__main__":
    create_indices()