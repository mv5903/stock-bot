import sqlite3
import pandas as pd
import os
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score
from dotenv import load_dotenv

load_dotenv()



def pick_top_Stock(n = int(os.getenv("TOP_N_STOCKS"))):
    # Load environment variables
    plot_path = os.getenv("PLOT_OUTPUT_PATH")
    valuation = os.getenv("VALUATION")

    if plot_path is None:
        print("Error: Plot output path not found in environment variables.")
        print("Please set PLOT_OUTPUT_PATH in your .env file.")
        print("It should be a relative path to the directory where you want to save the plots, such as \"./plots/\".")
        exit(1)

    # Create the directory if it doesn't exist
    if not os.path.exists(plot_path):
        os.makedirs(plot_path)

    # Delete all .png files in the directory
    for file in os.listdir(plot_path):
        if file.endswith(".png"):
            os.remove(os.path.join(plot_path, file))


    ############################################
    # Load Data from Database
    ############################################

    # Connect to the SQLite database
    db_path = os.getenv("DB_PATH")
    conn = sqlite3.connect(db_path)

    # Load tech_stocks that have valuation data
    df_stocks = pd.read_sql_query(f"SELECT * FROM tech_stocks WHERE valuation == \"{valuation}\";", conn)

    # Load news and sentiments, and join them
    # We want to aggregate sentiment by ticker
    df_news = pd.read_sql_query("SELECT * FROM news;", conn)
    df_sentiments = pd.read_sql_query("SELECT * FROM sentiments;", conn)

    # Join sentiments with news on article_id = news.id
    df_news_sent = pd.merge(df_news, df_sentiments, left_on='id', right_on='article_id', how='inner')

    # Aggregate sentiment scores by ticker
    # We'll use mean of score_compound as a simple aggregated sentiment measure
    df_ticker_sentiment = df_news_sent.groupby('ticker', as_index=False).agg({
        'score_compound': 'mean'
    }).rename(columns={'score_compound': 'avg_compound_sentiment'})

    conn.close()

    ############################################
    # Feature Engineering
    ############################################

    # Merge sentiment data with the stocks data
    df = pd.merge(df_stocks, df_ticker_sentiment, left_on='symbol', right_on='ticker', how='left')
    df.drop('ticker', axis=1, inplace=True)  # ticker came from sentiments join, symbol is the main key

    # Replace NaN sentiment with 0 if no articles found
    df['avg_compound_sentiment'] = df['avg_compound_sentiment'].fillna(0)

    # Create target variable: future_return = (future_price - current_price) / current_price
    df['future_return'] = (df['intrinsic_value'] - df['current_price']) / df['current_price']

    # For modeling, let's pick some key features:
    # We'll use valuation_gap, avg_compound_sentiment, market_cap, pe_ratio, revenue_growth as an example.
    features = ['valuation_gap', 'avg_compound_sentiment', 'market_cap']
    target = 'future_return'

    # Filter rows where we have no future price or current price
    df = df.dropna(subset=['future_return'] + features)

    # Correlation Matrix
    corr_cols = features + [target]
    corr = df[corr_cols].corr()


    ############################################
    # Modeling
    ############################################
    X = df[features]
    y = df[target]

    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Train a Random Forest Regressor
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)

    # Predict on test set
    y_pred = model.predict(X_test)

    # Evaluate
    r2 = r2_score(y_test, y_pred)

    # Plot Predicted vs Actual

    # Draw a reference line y=x
    mn = min(y_test.min(), y_pred.min())
    mx = max(y_test.max(), y_pred.max())


    # Feature Importance
    importances = model.feature_importances_
    imp_df = pd.DataFrame({'feature': features, 'importance': importances})
    imp_df = imp_df.sort_values('importance', ascending=False)


    # Connect to DB and get the latest stocks data
    conn = sqlite3.connect(db_path)
    df_latest = pd.read_sql_query("SELECT * FROM tech_stocks WHERE valuation == \"undervalued\";", conn)

    # Also get latest sentiment data
    df_news = pd.read_sql_query("SELECT * FROM news;", conn)
    df_sents = pd.read_sql_query("SELECT * FROM sentiments;", conn)
    conn.close()

    df_ns = pd.merge(df_news, df_sents, left_on='id', right_on='article_id', how='inner')
    df_latest_sent = df_ns.groupby('ticker', as_index=False).agg({'score_compound': 'mean'}).rename(columns={'score_compound': 'avg_compound_sentiment'})
    df_latest = pd.merge(df_latest, df_latest_sent, left_on='symbol', right_on='ticker', how='left').drop('ticker', axis=1)
    df_latest['avg_compound_sentiment'] = df_latest['avg_compound_sentiment'].fillna(0)

    # Prepare feature matrix
    # Note: We are predicting future_return, even though we may not have future_price yet. 
    # The idea is that the model gives us a predicted score, and we rank by it.
    X_live = df_latest[features].fillna(0)  # Fill NaNs if any

    df_latest['predicted_return'] = model.predict(X_live)

    # Sort by predicted return
    df_top = df_latest.sort_values('predicted_return', ascending=False).head(n)

    df_top.reset_index(drop=True, inplace=True)
    df_top.index = df_top.index + 1 # Start at 1, not 0

    return df_top[['symbol', 'current_price']]
