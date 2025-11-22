import psycopg2
import psycopg2.extras
from config import DB_CONFIG
from database_utils import create_portfolio_tables, add_transaction, get_portfolio_holdings, get_portfolio_transactions

def test_portfolio_db():
    print("Testing Portfolio Database...")
    
    # 1. Create Tables
    print("Creating tables...")
    create_portfolio_tables(DB_CONFIG)
    
    # 2. Create a Test Portfolio (Direct SQL for now as we didn't add a function for this yet)
    print("Creating test portfolio...")
    portfolio_id = None
    try:
        with psycopg2.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO portfolios (name) VALUES ('Test Portfolio') RETURNING id")
                portfolio_id = cursor.fetchone()[0]
                conn.commit()
        print(f"Created portfolio with ID: {portfolio_id}")
    except Exception as e:
        print(f"Error creating portfolio: {e}")
        return

    # 3. Add BUY Transaction
    print("Adding BUY transaction...")
    # Buy 100 shares of TEST.JO at R10.00 (1000 cents)
    success = add_transaction(DB_CONFIG, portfolio_id, 'TEST.JO', 'BUY', 100, 10.00, 50.00)
    if success:
        print("BUY transaction added successfully.")
    else:
        print("Failed to add BUY transaction.")

    # 4. Verify Holdings
    print("Verifying holdings...")
    holdings = get_portfolio_holdings(DB_CONFIG, portfolio_id)
    print(f"Holdings: {holdings}")
    # Expected: [{'ticker': 'TEST.JO', 'quantity': 100, 'average_buy_price': 10.00}]
    
    # 5. Add SELL Transaction
    print("Adding SELL transaction...")
    # Sell 50 shares of TEST.JO at R12.00
    success = add_transaction(DB_CONFIG, portfolio_id, 'TEST.JO', 'SELL', 50, 12.00, 50.00)
    if success:
        print("SELL transaction added successfully.")
    else:
        print("Failed to add SELL transaction.")

    # 6. Verify Holdings Again
    print("Verifying holdings after sell...")
    holdings = get_portfolio_holdings(DB_CONFIG, portfolio_id)
    print(f"Holdings: {holdings}")
    # Expected: [{'ticker': 'TEST.JO', 'quantity': 50, 'average_buy_price': 10.00}] (Avg price shouldn't change on sell usually, or depends on accounting method. FIFO/Weighted Avg. For simple avg buy price, it usually stays same or we need complex logic. Let's see implementation.)

    # 7. Verify Transactions
    print("Verifying transactions...")
    transactions = get_portfolio_transactions(DB_CONFIG, portfolio_id)
    print(f"Transactions: {len(transactions)} found.")
    for t in transactions:
        print(t)

    # Cleanup (Optional, maybe keep for inspection)
    # with psycopg2.connect(**DB_CONFIG) as conn:
    #     with conn.cursor() as cursor:
    #         cursor.execute("DELETE FROM portfolio_transactions WHERE portfolio_id = %s", (portfolio_id,))
    #         cursor.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = %s", (portfolio_id,))
    #         cursor.execute("DELETE FROM portfolios WHERE id = %s", (portfolio_id,))
    #         conn.commit()
    # print("Cleanup complete.")

if __name__ == "__main__":
    test_portfolio_db()
