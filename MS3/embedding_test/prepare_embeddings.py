from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
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
# Helper: Semantic Text Builder
# ------------------------------
def build_semantic_text(record):
    """
    Constructs a qualitative narrative using the provided airline metrics.
    Now optimized for 'Route' phrasing and 'Record Lookup'.
    """
    # --- Delay Context ---
    delay = record['arrival_delay_minutes']
    if delay <= 0:
        delay_desc = f"arrived early by {abs(delay)} minutes"
        punctuality = "highly punctual"
    elif delay <= 15:
        delay_desc = f"was roughly on time ({delay} min delay)"
        punctuality = "punctual"
    elif delay <= 60:
        delay_desc = f"had a moderate delay of {delay} minutes"
        punctuality = "delayed"
    else:
        delay_desc = f"suffered a severe delay of {delay} minutes"
        punctuality = "severely delayed"

    # --- Food Context ---
    score = record['food_satisfaction_score']
    if score <= 2:
        food_desc = "poor dining experience"
    elif score == 3:
        food_desc = "average dining experience"
    else:
        food_desc = "excellent dining experience"

    # --- Distance Context ---
    miles = record['actual_flown_miles']
    if miles < 1000:
        haul = "short-haul"
    elif miles < 4000:
        haul = "medium-haul"
    else:
        haul = "long-haul"

    # --- Construct the Sentence ---
    # CHANGES:
    # 1. Added explicit "Record Locator" sentence for lookup support.
    # 2. Added "out of" and "from/to" phrasing to boost route matching.
    text = (
        f"A {punctuality} {haul} flight operating out of {record['origin']}. "
        f"The flight departs from {record['origin']} and arrives at {record['destination']}. "
        f"The {record['passenger_class']} journey covered {miles} miles on a {record['fleet_type_description']} aircraft. "
        f"It {delay_desc}. "
        f"The passenger (Generation: {record['generation']}, Status: {record['loyalty_program_level']}) "
        f"reported a {food_desc} with a rating of {score}/5. "
        f"Passenger record locator is {record['record_locator']} and Feedback ID is {record['feedback_ID']}."
    )
    return text

# ------------------------------
# 3. Processing Pipeline
# ------------------------------
def process(tx):
    print("Fetching journey data...")
    result = tx.run("""
        MATCH (p:Passenger)-[:TOOK]->(j:Journey)-[:ON]->(f:Flight)
        MATCH (f)-[:DEPARTS_FROM]->(dep:Airport)
        MATCH (f)-[:ARRIVES_AT]->(arr:Airport)
        RETURN
            j.feedback_ID AS feedback_ID,
            p.record_locator AS record_locator,
            p.generation AS generation,
            p.loyalty_program_level AS loyalty_program_level,
            j.food_satisfaction_score AS food_satisfaction_score,
            j.arrival_delay_minutes AS arrival_delay_minutes,
            j.actual_flown_miles AS actual_flown_miles,
            j.passenger_class AS passenger_class,
            f.fleet_type_description AS fleet_type_description,
            dep.station_code AS origin,
            arr.station_code AS destination
    """)
    
    records = list(result)
    print(f"Found {len(records)} journeys to embed.")

    for i, row in enumerate(records):
        # 1. Build rich text with  route/ID phrasing
        text = build_semantic_text(row)

        # 2. Generate embeddings
        emb_minilm = model_minilm.encode(text).tolist()
        emb_mpnet = model_mpnet.encode(text).tolist()
        emb_bge_m3 = model_bge_m3.encode(text).tolist()

        # 3. Store in SEPARATE Node (:JourneyVector)
        tx.run("""
            MATCH (j:Journey {feedback_ID: $fid})
            
            MERGE (jv:JourneyVector {id: $fid + '_vec'})
            ON CREATE SET 
                jv.text = $text,
                jv.record_locator = $locator,  
                jv.feedback_id = $fid,         
                jv.minilm_embedding = $e1,
                jv.mpnet_embedding = $e2,
                jv.bgem3_embedding = $e3
            ON MATCH SET
                jv.text = $text,
                jv.record_locator = $locator,
                jv.feedback_id = $fid,
                jv.minilm_embedding = $e1,
                jv.mpnet_embedding = $e2,
                jv.bgem3_embedding = $e3
            
            MERGE (j)-[:HAS_VECTOR]->(jv)
        """, 
        fid=row['feedback_ID'],
        locator=row['record_locator'],
        text=text,
        e1=emb_minilm, 
        e2=emb_mpnet, 
        e3=emb_bge_m3)

        if i % 50 == 0:
            print(f"Processed {i}/{len(records)}...")

with driver.session() as session:
    session.execute_write(process)

print("Done! Vectors stored in 'JourneyVector' nodes.")