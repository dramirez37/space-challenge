# =========================================================================
# Author:   David Ramirez
# Purpose:  Generate visual aids for the final report
# =========================================================================
import os
import pandas as pd
import matplotlib.pyplot as plt
from sqlalchemy import create_engine, text

def generate_visuals():
    """
    Connects to the database to generate a Markdown table of the top agents
    and a bar chart of the model's feature importance.
    """
    # 1. Connect to the database
    db_password = os.environ.get('PASSWORD')
    if not db_password:
        raise ValueError("Database password not found in environment variable 'PASSWORD'")

    connection_string = (
        f"mssql+pyodbc://SA:{db_password}@localhost,1435/master"
        f"?driver=ODBC+Driver+17+for+SQL+Server"
    )
    engine = create_engine(connection_string)
    print("Successfully connected to the database.")

    # Create a results directory if it doesn't exist
    os.makedirs('results', exist_ok=True)

    # 2. Generate the Test Output Table
    print("Running test query to generate agent rankings...")
    test_sql = """
    EXEC dbo.AssignBestAgents
        @CustomerName       = 'Test User',
        @CommunicationMethod= 'Phone Call',
        @LeadSource         = 'Organic',
        @Destination        = 'Mars',
        @LaunchLocation     = 'Earth Orbital Station',
        @Requirements       = 'Luxury Dome Stay';
    """
    df_ranks = pd.read_sql_query(text(test_sql), engine)
    
    # Save the results to the results folder
    with open("results/test_output.md", "w") as f:
        f.write(df_ranks.to_markdown(index=False))
    print("Successfully created 'results/test_output.md' with agent rankings.")

    # 3. Generate the Feature Importance Graph
    print("Querying feature weights for the graph...")
    weights_sql = "SELECT FeatureName, Weight FROM dbo.learned_weights_table"
    df_weights = pd.read_sql_query(text(weights_sql), engine).sort_values(by="Weight", ascending=True)

    # Create the horizontal bar chart
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(df_weights['FeatureName'], df_weights['Weight'], color='skyblue')
    ax.set_title('Feature Importance', fontsize=16)
    ax.set_xlabel('Weight')
    ax.axvline(0, color='grey', linewidth=0.8) # Add a line at zero
    plt.tight_layout()
    
    # Save the chart to the results folder
    plt.savefig('results/feature_importance.png')
    print("Successfully saved 'results/feature_importance.png'.")

if __name__ == "__main__":
    generate_visuals()