import psycopg2
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'gui'))
from core.config import DB_CONFIG

def check_prices():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT ticker, close_price FROM daily_stock_data WHERE ticker LIKE 'HAR%%' LIMIT 5")
        res = cur.fetchall()
        print(f"Sample Prices: {res}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    check_prices()
