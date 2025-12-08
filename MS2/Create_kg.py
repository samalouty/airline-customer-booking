import pandas as pd
from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

load_dotenv()

def create_kg():
    uri = os.getenv('NEO4J_URI', 'neo4j://localhost:7687')
    username = os.getenv('NEO4J_USERNAME', 'neo4j')
    password = os.getenv('NEO4J_PASSWORD', 'password')

    driver = GraphDatabase.driver(uri, auth=(username, password))

    csv_file = 'Airline_surveys_sample.csv'
    df = pd.read_csv(csv_file)

    with driver.session() as session:

        for index, row in df.iterrows():
            # Passenger
            record_locator = row['record_locator']
            loyalty_program_level = row['loyalty_program_level']
            generation = row['generation']

            # Journey
            feedback_ID = row['feedback_ID']
            food_satisfaction_score = int(row['food_satisfaction_score'])
            arrival_delay_minutes = int(row['arrival_delay_minutes'])
            actual_flown_miles = int(row['actual_flown_miles'])
            number_of_legs = int(row['number_of_legs'])
            passenger_class = row['passenger_class']

            # Flight
            flight_number = str(row['flight_number']) # Treat as string to be safe or int
            fleet_type_description = row['fleet_type_description']

            # Airports
            origin_code = row['origin_station_code']
            dest_code = row['destination_station_code']

            query = """
            MERGE (p:Passenger {record_locator: $record_locator})
            SET p.loyalty_program_level = $loyalty_program_level,
                p.generation = $generation
            
            
            MERGE (j:Journey {feedback_ID: $feedback_ID})
            SET j.food_satisfaction_score = $food_satisfaction_score,
                j.arrival_delay_minutes = $arrival_delay_minutes,
                j.actual_flown_miles = $actual_flown_miles,
                j.number_of_legs = $number_of_legs,
                j.passenger_class = $passenger_class

            MERGE (f:Flight {flight_number: $flight_number, fleet_type_description: $fleet_type_description})

            MERGE (origin:Airport {station_code: $origin_code})
            MERGE (dest:Airport {station_code: $dest_code})

            MERGE (p)-[:TOOK]->(j)
            MERGE (j)-[:ON]->(f)
            MERGE (f)-[:DEPARTS_FROM]->(origin)
            MERGE (f)-[:ARRIVES_AT]->(dest)
            """

            session.run(query,
                        record_locator=record_locator,
                        loyalty_program_level=loyalty_program_level,
                        generation=generation,
                        feedback_ID=feedback_ID,
                        food_satisfaction_score=food_satisfaction_score,
                        arrival_delay_minutes=arrival_delay_minutes,
                        actual_flown_miles=actual_flown_miles,
                        number_of_legs=number_of_legs,
                        passenger_class=passenger_class,
                        flight_number=flight_number,
                        fleet_type_description=fleet_type_description,
                        origin_code=origin_code,
                        dest_code=dest_code
                        )
            
            if index % 100 == 0:
                print(f"Processed {index} rows...")

    driver.close()
    print("Knowledge Graph created successfully. 🥳")

if __name__ == "__main__":
    create_kg()
