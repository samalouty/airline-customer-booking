import re
from neo4j import GraphDatabase

def load_config(config_file):
    config = {}
    with open(config_file, 'r') as f:
        for line in f:
            if '=' in line:
                key, value = line.strip().split('=', 1)
                config[key] = value
    return config

def parse_queries(file_path):
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Split by query headers (e.g., "// 1. Query 1", "// 5. Query")
    # We use a regex that matches the pattern of the headers
    parts = re.split(r'// \d+\. Query.*', content)
    
    queries = []
    for part in parts:
        # Remove comments (lines starting with //) and strip whitespace
        lines = [line for line in part.splitlines() if not line.strip().startswith('//')]
        query = '\n'.join(lines).strip()
        if query:
            queries.append(query)
    return queries

def run_queries():
    config = load_config('config.txt')
    uri = config.get('URI', 'neo4j://localhost:7687')
    username = config.get('USERNAME', 'neo4j')
    password = config.get('PASSWORD', 'password')

    driver = GraphDatabase.driver(uri, auth=(username, password))

    queries = parse_queries('queries.txt')
    
    print(f"Found {len(queries)} queries to execute.\n")

    with driver.session() as session:
        for i, query in enumerate(queries, 1):
            print(f"--- Running Query {i} ---")
            print(f"Query:\n{query}\n")
            try:
                result = session.run(query)
                records = list(result)
                if not records:
                    print("No results found.")
                else:
                    # Print header
                    keys = records[0].keys()
                    print(" | ".join(keys))
                    print("-" * (len(keys) * 15))
                    
                    # Print rows
                    for record in records:
                        print(" | ".join(str(record[key]) for key in keys))
            except Exception as e:
                print(f"Error running query {i}: {e}")
            print("\n" + "="*30 + "\n")

    driver.close()

if __name__ == "__main__":
    run_queries()
