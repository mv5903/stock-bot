import sqlite3
import os
import sys
from dotenv import load_dotenv

load_dotenv()

SQLITE_DATABASE_PATH = os.getenv("DB_PATH")

# Make sure the file exists
if (not os.path.exists(SQLITE_DATABASE_PATH)):
    print(f"Error: SQLite file not found at {SQLITE_DATABASE_PATH}")
    sys.exit(1)

# Connect to your SQLite database file.
conn = sqlite3.connect(SQLITE_DATABASE_PATH)

# Get a cursor object
cur = conn.cursor()

# Create a test table
cur.execute("""
CREATE TABLE IF NOT EXISTS test (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL NOT NULL
);
""")

# Insert some test data
cur.execute("INSERT INTO test (name, value) VALUES ('test1', 1.0)")

# Fetch all results
results = cur.execute("SELECT * FROM test").fetchall()

# Drop the test table
cur.execute("DROP TABLE test")

print("Test complete")

# Close the connection
conn.close()