from neo4j import GraphDatabase

# ------------------------------
# Neo4j Connection
# ------------------------------
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

# ------------------------------
# Create Vector Indices
# ------------------------------
def create_indices():
    with driver.session() as session:
        print("Creating vector indices...")
        
        # 1. MiniLM index (384 dimensions)
        print("Creating journey_minilm_full_index...")
        session.run("""
            CREATE VECTOR INDEX journey_minilm_full_index IF NOT EXISTS
            FOR (j:Journey)
            ON j.embedding_minilm_full
            OPTIONS { indexConfig: { `vector.dimensions`: 384, `vector.similarity_function`: "cosine" } }
        """)
        
        # 2. MPNet index (768 dimensions)
        print("Creating journey_mpnet_full_index...")
        session.run("""
            CREATE VECTOR INDEX journey_mpnet_full_index IF NOT EXISTS
            FOR (j:Journey)
            ON j.embedding_mpnet_full
            OPTIONS { indexConfig: { `vector.dimensions`: 768, `vector.similarity_function`: "cosine" } }
        """)
        
        # 3. BGE-M3 index (1024 dimensions)
        print("Creating journey_bge_m3_index...")
        session.run("""
            CREATE VECTOR INDEX journey_bge_m3_index IF NOT EXISTS
            FOR (j:Journey)
            ON j.embedding_bge_m3_full
            OPTIONS { indexConfig: { `vector.dimensions`: 1024, `vector.similarity_function`: "cosine" } }
        """)
        
        print("\nAll vector indices created successfully!")
        
        # Show all indices
        print("\nListing all indices:")
        result = session.run("SHOW INDEXES")
        for record in result:
            print(f"  - {record['name']}: {record['type']} on {record['labelsOrTypes']}")

create_indices()
driver.close()
