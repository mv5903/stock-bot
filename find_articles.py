# https://finnhub.io/docs/api/market-news

import finnhub
import os
import sqlite3
from dotenv import load_dotenv
from datetime import date, timedelta
import time

load_dotenv()

SQLITE_DATABASE_PATH = os.getenv("DB_PATH")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")

conn = sqlite3.connect(SQLITE_DATABASE_PATH)

finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)

n_days_ago = 10 # Free tier limit is 365 days, determines how many days back to fetch news from

from_date = (date.today() - timedelta(days=n_days_ago)).isoformat()
to_date = date.today().isoformat()

cur = conn.cursor()

tickers = conn.execute("SELECT symbol FROM tech_stocks WHERE market_cap > 2000000000 AND valuation = \"undervalued\"").fetchall()
tickers = [ticker[0] for ticker in tickers] # convert from list of tuples to list of strings

print(f"Found {len(tickers)} tech stocks in the database.")

# Create the news table
cur.execute("""
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    category TEXT,
    datetime TEXT NOT NULL,
    headline TEXT NOT NULL,
    image TEXT,
    related TEXT,
    source TEXT NOT NULL,
    summary TEXT,
    url TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticker) REFERENCES tech_stocks(symbol),
    UNIQUE (ticker, datetime, headline, source)
);
""")

# Fetch news for each ticker
ticker_count = 1
for ticker in tickers:
    result = finnhub_client.company_news(ticker, _from=from_date, to=to_date)

    insert_count = 0
    skip_count = 0

    # For every article found, insert into the database
    for article in result:
        cur.execute("""
        INSERT OR IGNORE INTO news (ticker, category, datetime, headline, image, related, source, summary, url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            ticker,
            article.get("category"),
            article.get("datetime"),
            article.get("headline"),
            article.get("image"),
            article.get("related"),
            article.get("source"),
            article.get("summary"),
            article.get("url")
        ))

        if cur.rowcount > 0:  # Check if a row was actually inserted
            insert_count += 1
        else:
            skip_count += 1

    time.sleep(1.05) # Sleep for 1.05 seconds to avoid rate limiting

    # Commit the changes after processing all articles for this ticker
    conn.commit()

    # Print the summary for this ticker
    print(f"{ticker} (#{ticker_count}):\tFound {len(result)} articles, inserted {insert_count} new articles, skipped {skip_count} duplicate articles.")
    ticker_count += 1

# Close the connection
conn.close()




