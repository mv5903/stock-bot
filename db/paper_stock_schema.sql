CREATE TABLE IF NOT EXISTS users {
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    passwrd VARCHAR(255) NOT NULL,
    created_dt TIMESTAMP DEFAULT CURRENT_TIMESTAMP

}

CREATE TABLE IF NOT EXISTS stocks {
    stock_id SERIAL PRIMARY KEY,
    ticker_symbol VARCHAR(10) NOT NULL UNIQUE,
    company_name VARCHAR(255) NOT NULL,
    created_dt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
}

CREATE TABLE IF NOT EXISTS paper_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_symbol TEXT NOT NULL,
    trade_type TEXT CHECK(trade_type IN ('buy', 'sell')) NOT NULL,
    quantity INTEGER NOT NULL,
    price REAL NOT NULL,
    trade_date TEXT NOT NULL,
    trade_status TEXT CHECK(trade_status IN ('open', 'closed')) NOT NULL
);
-- Table: portfolio
CREATE TABLE portfolio (
    portfolio_id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_symbol TEXT NOT NULL,
    week_start_date DATE NOT NULL,
    week_end_date DATE NOT NULL,
    total_quantity INT NOT NULL DEFAULT 0,
    total_cost DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    weekly_profit_loss DECIMAL(15, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS top_stocks {
    run_id SERIAL PRIMARY KEY,
    run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    stock_id INT REFERENCES stocks(stock_id),
    rank INT NOT NULL (rank >= 1)
}



