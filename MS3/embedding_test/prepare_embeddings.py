from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import numpy as np
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ------------------------------
# 1. Load Embedding Models
# ------------------------------
print("Loading embedding models...")
model_minilm = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
model_mpnet = SentenceTransformer("sentence-transformers/paraphrase-mpnet-base-v2")
model_bge_m3 = SentenceTransformer("BAAI/bge-m3")


# ------------------------------
# 2. Neo4j Connection
# ------------------------------
uri = os.getenv('NEO4J_URI', 'neo4j://localhost:7687')
username = os.getenv('NEO4J_USERNAME', 'neo4j')
password = os.getenv('NEO4J_PASSWORD', 'password')

driver = GraphDatabase.driver(uri, auth=(username, password))

# ------------------------------
# Helper: Create Complete Feature Text
# ------------------------------
def build_feature_text(record):
    return (
        f"Passenger {record['record_locator']} with loyalty level {record['loyalty_program_level']} "
        f"and generation {record['generation']} took Journey {record['feedback_ID']}. "
        f"The journey had food satisfaction score {record['food_satisfaction_score']}, "
        f"arrival delay of {record['arrival_delay_minutes']} minutes, "
        f"actual flown miles {record['actual_flown_miles']}, "
        f"{record['number_of_legs']} legs, in {record['passenger_class']} class. "
        f"The journey was on Flight {record['flight_number']} which used {record['fleet_type_description']} "
        f"aircraft, departing from {record['origin']} and arriving at {record['destination']}."
    )



# ------------------------------
# 3. Generate Embeddings for Journeys
# ------------------------------
def process(tx):
    result = tx.run("""
        MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
        MATCH (f)-[:DEPARTS_FROM]->(dep:Airport)
        MATCH (f)-[:ARRIVES_AT]->(arr:Airport)
        RETURN
            elementId(j) AS jid,
            p.record_locator AS record_locator,
            p.loyalty_program_level AS loyalty_program_level,
            p.generation AS generation,
            j.feedback_ID AS feedback_ID,
            j.food_satisfaction_score AS food_satisfaction_score,
            j.arrival_delay_minutes AS arrival_delay_minutes,
            j.actual_flown_miles AS actual_flown_miles,
            j.number_of_legs AS number_of_legs,
            j.passenger_class AS passenger_class,
            f.flight_number AS flight_number,
            f.fleet_type_description AS fleet_type_description,
            dep.station_code AS origin,
            arr.station_code AS destination

    """)

    for i, row in enumerate(result):
        text = build_feature_text(row)

        emb_minilm = model_minilm.encode(text).tolist()
        emb_mpnet = model_mpnet.encode(text).tolist()
        emb_bge_m3 = model_bge_m3.encode(text).tolist()

        tx.run("""
            MATCH (j:Journey)
            WHERE elementId(j) = $jid
            SET j.full_feature_text = $text,
                j.embedding_minilm_full = $emb_minilm,
                j.embedding_mpnet_full = $emb_mpnet,
                j.embedding_bge_m3_full = $emb_bge_m3
        """,
        jid=row["jid"],
        text=text,
        emb_minilm=emb_minilm,
        emb_mpnet=emb_mpnet,
        emb_bge_m3=emb_bge_m3)
        
        if i % 100 == 0:
            print(i, "- Embedded Journey", row["feedback_ID"])
        
# Run the embedding pipeline
with driver.session() as session:
    session.execute_write(process)

print("\nEmbeddings generated and stored successfully!")
