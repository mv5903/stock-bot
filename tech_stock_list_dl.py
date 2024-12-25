import requests
import sqlite3
import os
import sys
import json
from dotenv import load_dotenv
from collections import Counter

# Load environment variables
load_dotenv()

# API configuration
URL = "https://api.stockanalysis.com/api/screener/s/f?m=marketCap&s=desc&c=no,s,n,marketCap,sector&cn=0&f=exchange-is-NASDAQ&p=1&i=stocks&sc=marketCap"

# SQLite configuration
SQLITE_DATABASE_PATH = os.getenv("DB_PATH")
if not os.path.exists(SQLITE_DATABASE_PATH):
    print(f"Error: SQLite file not found at {SQLITE_DATABASE_PATH}")
    sys.exit(1)

# Fetch data from API
data = []
url = URL
response = requests.get(url)
response_data = response.json().get("data", {}).get("data", [])
data.extend(response_data)

print(f"Total stocks fetched: {len(data)}")

# Count occurrences of symbols to detect duplicates, in case there are any
symbol_counts = Counter(stock.get("s") for stock in data if stock.get("s"))
duplicates = {symbol: count for symbol, count in symbol_counts.items() if count > 1}

# Log duplicates, in case there are any
if duplicates:
    print(f"Found {len(duplicates)} duplicate symbols:")
    for symbol, count in duplicates.items():
        print(f"  {symbol}: {count} occurrences")

# Filter for technology sector and deduplicate by 'symbol'
tech_stocks = [stock for stock in data if stock.get("sector") == "Technology"]
unique_stocks = {stock["s"]: stock for stock in tech_stocks if stock.get("s")}.values()
print(f"Found {len(tech_stocks)} technology stocks")
print(f"Unique technology stocks after deduplication: {len(unique_stocks)}")

# Connect to SQLite database
conn = sqlite3.connect(SQLITE_DATABASE_PATH)
cur = conn.cursor()

# Create the tech_stocks table
cur.execute("""
CREATE TABLE IF NOT EXISTS tech_stocks (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    market_cap REAL,
    sector TEXT, 
    current_eps REAL,
    projected_eps REAL,
    stock_pe_ratio_forward REAL,
    stock_pe_ratio_trailing REAL,
    earnings_growth REAL,
    dividend_yield REAL,
    beta REAL,
    current_price REAL,
    intrinsic_value REAL,
    fair_value REAL,
    valuation_gap REAL,
    valuation TEXT
);
""")

# Insert stocks into the database
inserted_count = 0
skipped_stocks = []
for stock in unique_stocks:
    try:
        cur.execute("""
        INSERT OR REPLACE INTO tech_stocks (
            symbol, name, market_cap, sector
        ) VALUES (?, ?, ?, ?);
        """, (
            stock.get("s"),
            stock.get("n"),
            stock.get("marketCap"),
            stock.get("sector"),
        ))
        inserted_count += 1
    except sqlite3.Error as e:
        print(f"Error inserting stock {stock.get('s')}: {e}")
        skipped_stocks.append(stock.get("s"))

# Commit and close the connection
conn.commit()
cur.execute("SELECT COUNT(*) FROM tech_stocks;")
row_count = cur.fetchone()[0]
conn.close()

# Final output
print(f"Data inserted: {inserted_count} stocks successfully into tech_stocks table.")
print(f"Number of records in the database: {row_count}")
if skipped_stocks:
    print(f"Skipped {len(skipped_stocks)} stocks: {skipped_stocks}")
