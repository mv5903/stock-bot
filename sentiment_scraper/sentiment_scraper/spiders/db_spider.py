import scrapy
import sqlite3
from newspaper import Article
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from dotenv import load_dotenv
import os

class DBSpider(scrapy.Spider):
    name = 'db_spider'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        load_dotenv()
        self.db_path = "../" + os.getenv("DB_PATH")

    def start_requests(self):
        # Connect to the database
        print(self.db_path)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sentiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER,
            url TEXT,
            score_neg REAL,
            score_neu REAL,
            score_pos REAL,
            score_compound REAL,
            overall_sentiment TEXT,
            FOREIGN KEY (article_id) REFERENCES news(id),
            UNIQUE (article_id)
        )
        """
        )
        conn.commit()

        # Fetch article URLs from the `news` table
        cursor.execute("SELECT id, url FROM news")
        rows = cursor.fetchall()

        conn.close()

        # Pass article_id along with the request
        count = 1
        for row in rows:
            print(f"\rProcessing article {count}/{len(rows)} ({count / len(rows) * 100}%)", end="")
            count += 1
            row_id = row[0]
            url = row[1]
            yield scrapy.Request(
                url=url, 
                callback=self.parse,
                cb_kwargs={'article_id': row_id}
            )

    def parse(self, response, article_id):
        # Extract main content using newspaper3k
        article = Article(response.url)
        article.set_html(response.text)
        article.parse()
        full_text = article.text

        # Sentiment analysis
        sid = SentimentIntensityAnalyzer()
        scores = sid.polarity_scores(full_text)
        overall_sentiment = self.interpret_sentiment(scores['compound'])

        # Insert data into the database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO sentiments (article_id, url, score_neg, score_neu, score_pos, score_compound, overall_sentiment)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (article_id, response.url, scores['neg'], scores['neu'], scores['pos'], scores['compound'], overall_sentiment)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            self.logger.warning(f"Article ID {article_id} already exists in sediments.")
        finally:
            conn.close()

    def interpret_sentiment(self, compound_score):
        if compound_score >= 0.05:
            return "positive"
        elif compound_score <= -0.05:
            return "negative"
        else:
            return "neutral"
