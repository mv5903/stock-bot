import sys
import sqlite3
import pandas as pd
import yfinance as yf
import os
from top_stock import pick_top_Stock
from datetime import datetime
from dotenv import load_dotenv, set_key


load_dotenv()


# Function to insert paper trade record into the database
def insert_trade(conn, stock_symbol, trade_type, quantity, price, trade_status="open"):
    trade_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO paper_trades (stock_symbol, trade_type, quantity, price, trade_date, trade_status)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
        (stock_symbol, trade_type, quantity, price, trade_date, trade_status),
    )
    conn.commit()


# Modified function to pick top stocks and insert paper trades
def create_paper_trades_from_top_stocks(
    n=int(os.getenv("TOP_N_STOCKS")), quantity=int(os.getenv("TOP_STOCKS_QUANTITY"))
):
    # Run the pick_top_stocks function to get top stocks
    df_top_stocks = pick_top_Stock(n)

    # Connect to the database
    db_path = os.getenv("DB_PATH")
    conn = sqlite3.connect(db_path)

    # Loop through the top n stocks and create paper trades
    for _, row in df_top_stocks.iterrows():
        stock_symbol = row["symbol"]
        predicted_return = row["current_price"]

        # Assume a basic trading strategy: buying the stock
        trade_type = "buy"

        # Use the predicted return to determine a rough price (this is just an example)
        # In a real-world scenario, you would get the actual price from a stock data API or the DB
        stock_price = predicted_return  # Assuming a base price of $100 for simplicity

        # Insert the trade into the database
        insert_trade(conn, stock_symbol, trade_type, quantity, stock_price)

    # Close the database connection
    conn.close()


def get_current_price(stock_symbol):
    current_price = 0
    stock = yf.Ticker(stock_symbol)
    current_price = stock.info.get("currentPrice", 0.0)
    return current_price


def get_current_stocks_profit_loss(stock_symbols=None):
    try:
        # Connect to the database
        db_path = os.getenv("DB_PATH")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if stock_symbols:
            stock_symbols = [symbol.strip() for symbol in stock_symbols]
            query = (
                """
                    SELECT id, stock_symbol, quantity, price, trade_date
                    FROM paper_trades
                    WHERE trade_status = 'open' and stock_symbol IN ("""
                + ", ".join(["?"] * len(stock_symbols))
                + ")"
            )

            cursor.execute(query, stock_symbols)
        else:
            query = """
                    SELECT id, stock_symbol, quantity, price, trade_date
                    FROM paper_trades
                    WHERE trade_status = 'open';
                    """
            cursor.execute(query)

        active_trades = cursor.fetchall()

        # Convert to DataFrame
        df_active_trades = pd.DataFrame(
            active_trades,
            columns=["id", "stock_symbol", "quantity", "price", "trade_date"],
        )

        # Fetch current prices and calculate profit/loss
        df_active_trades["current_price"] = df_active_trades["stock_symbol"].apply(
            get_current_price
        )
        df_active_trades["total_gain_loss"] = (
            df_active_trades["current_price"] - df_active_trades["price"]
        ) * df_active_trades["quantity"]

        # print(df_active_trades)
        return df_active_trades

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def get_portfolio_for_week(date):
    try:
        # Connect to the database
        db_path = os.getenv("DB_PATH")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        query = """
            SELECT portfolio_id, stock_symbol, week_start_date, week_end_date, total_quantity, total_cost, weekly_profit_loss, created_at
            FROM portfolio
            WHERE week_start_date <= ? AND week_end_date >= ?; 
        """

        cursor.execute(
            query,
            (
                date,
                date,
            ),
        )
        results = cursor.fetchall()

        # Define column names for the DataFrame
        columns = [
            "portfolio_id",
            "stock_symbol",
            "week_start_date",
            "week_end_date",
            "total_quantity",
            "total_cost",
            "weekly_profit_loss",
            "created_at",
        ]

        # Convert the results to a DataFrame
        portfolio_df = pd.DataFrame(results, columns=columns)
        # print(portfolio_df)
        return portfolio_df

    except Exception as e:
        print(f"An error occurred: {e}")
        return None

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# Function to sell all open stocks, calculate gain/loss, and return a DataFrame
def sell_all_open_stocks_and_calculate_gains():
    # Connect to the database
    db_path = os.getenv("DB_PATH")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch all open trades
    cursor.execute(
        "SELECT id, stock_symbol, trade_type, quantity, price, trade_date FROM paper_trades WHERE trade_status = 'open'"
    )
    open_trades = cursor.fetchall()

    # Create a DataFrame from the fetched data
    df_open_trades = pd.DataFrame(
        open_trades,
        columns=["id", "stock_symbol", "trade_type", "quantity", "price", "trade_date"],
    )

    # Add a column for the current price (retrieved using the get_current_price function)
    df_open_trades["current_price"] = df_open_trades["stock_symbol"].apply(
        get_current_price
    )

    # Calculate gain/loss for each trade
    df_open_trades["gain_loss"] = (
        df_open_trades["current_price"] - df_open_trades["price"]
    ) * df_open_trades["quantity"]

    # Calculate the total cost
    df_open_trades["total_cost"] = df_open_trades["quantity"] * df_open_trades["price"]

    # Calculate start and end dates
    df_open_trades["week_start_date"] = pd.to_datetime(
        df_open_trades["trade_date"]
    ).dt.date
    df_open_trades["week_end_date"] = (
        pd.to_datetime(df_open_trades["trade_date"]) + pd.Timedelta(days=5)
    ).dt.date

    # Mark trades as 'closed' and update the database
    for _, row in df_open_trades.iterrows():
        cursor.execute(
            """
        UPDATE paper_trades
        SET trade_status = 'closed', trade_type = 'sell'           
        WHERE id = ?
        """,
            (row["id"],),
        )

    # Update the portfolio for weekly profit/loss
    for _, row in df_open_trades.iterrows():
        cursor.execute(
            """
        INSERT INTO portfolio(stock_symbol, week_start_date, week_end_date, total_quantity, total_cost, weekly_profit_loss)
        VALUES(?, ?, ?, ?, ?, ?);
                       
        """,
            (
                row["stock_symbol"],
                row["week_start_date"],
                row["week_end_date"],
                row["quantity"],
                row["total_cost"],
                row["gain_loss"],
            ),
        )

    cursor.execute("""
    DELETE FROM paper_trades
                   """)

    # Commit changes to the database
    conn.commit()

    # Close the connection
    conn.close()

    # Return the DataFrame with calculated gain/loss
    print(df_open_trades)
    return df_open_trades[
        ["stock_symbol", "quantity", "price", "current_price", "gain_loss"]
    ]


# get_portfolio_for_week("2023-11-31")
# get_current_stocks_profit_loss(["APP", "PTC", "NVDA"])
CRON_PATH = "../cronlogs/.env.cron"

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: script.py -B or -S")
        sys.exit(1)

    # Access arguments
    arg = sys.argv[1]

    if arg == "-B":
        # Create paper trades for the top 5 stocks
        create_paper_trades_from_top_stocks()
        # Notifies bot that the embed is ready to send
        set_key(CRON_PATH, "PAPER_BUY", "1")
    elif arg == "-S":
        sell_all_open_stocks_and_calculate_gains()
        set_key(CRON_PATH, "PAPER_SELL", "1")
    else:
        print(f"Invalid arguments recieved: {arg}")
