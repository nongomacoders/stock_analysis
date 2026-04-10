import psycopg2
from typing import Optional, List, Dict, Any
from core.config import DB_CONFIG

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def get_portfolio_by_name(name: str) -> Optional[int]:
    """Returns portfolio_id if it exists, otherwise None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM portfolios WHERE name = %s", (name,))
            row = cur.fetchone()
            return row[0] if row else None

def create_portfolio(name: str, initial_cash: float) -> int:
    """Creates a new portfolio and inserts initial cash. Returns the new ID."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("INSERT INTO portfolios (name) VALUES (%s) RETURNING id", (name,))
                portfolio_id = cur.fetchone()[0]
                
                # Initial cash as a 'BUY' of ZAR_CASH per special logic
                cur.execute(
                    """INSERT INTO portfolio_transactions (portfolio_id, ticker, transaction_type, quantity, price)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (portfolio_id, 'ZAR_CASH', 'BUY', initial_cash, 1.0)
                )
                
                _rebuild_holdings(cur, portfolio_id)
                conn.commit()
                return portfolio_id
            except Exception:
                conn.rollback()
                raise

def get_portfolio_holdings(portfolio_id: int) -> List[Dict[str, Any]]:
    """Returns holdings joined with latest available price."""
    query = """
    SELECT h.ticker, h.quantity, h.average_buy_price, d.close_price as market_price, d.trade_date as price_date
    FROM portfolio_holdings h
    LEFT JOIN (
        SELECT ticker, close_price, trade_date,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) as rn
        FROM daily_stock_data
    ) d ON (d.ticker = h.ticker OR d.ticker = h.ticker || '.JO' OR d.ticker = REPLACE(h.ticker, '.JO', '')) AND d.rn = 1
    WHERE h.portfolio_id = %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (portfolio_id,))
            rows = cur.fetchall()
            return [
                {
                    "ticker": r[0], "quantity": float(r[1]), "average_buy_price": float(r[2]),
                    "market_price": float(r[3]) if r[3] is not None else None, "price_date": r[4]
                }
                for r in rows
            ]

def get_portfolio_transactions(portfolio_id: int) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, ticker, transaction_type, quantity, price, transaction_date FROM portfolio_transactions WHERE portfolio_id = %s ORDER BY transaction_date DESC", (portfolio_id,))
            return [{"id":r[0], "ticker":r[1], "type":r[2], "quantity":float(r[3]), "price":float(r[4]), "date":r[5]} for r in cur.fetchall()]

def record_transaction(portfolio_id: int, ticker: str, tx_type: str, quantity: float, price: float):
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("INSERT INTO portfolio_transactions (portfolio_id, ticker, transaction_type, quantity, price) VALUES (%s, %s, %s, %s, %s)",
                           (portfolio_id, ticker, tx_type, quantity, price))
                _rebuild_holdings(cur, portfolio_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

def update_portfolio_transaction(tx_id: int, portfolio_id: int, ticker: str, tx_type: str, quantity: float, price: float):
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("UPDATE portfolio_transactions SET ticker=%s, transaction_type=%s, quantity=%s, price=%s WHERE id=%s AND portfolio_id=%s",
                           (ticker, tx_type, quantity, price, tx_id, portfolio_id))
                _rebuild_holdings(cur, portfolio_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

def delete_portfolio_transaction(tx_id: int, portfolio_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("DELETE FROM portfolio_transactions WHERE id = %s AND portfolio_id = %s", (tx_id, portfolio_id))
                _rebuild_holdings(cur, portfolio_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

def _rebuild_holdings(cur, portfolio_id: int):
    """Internal helper to rebuild holdings from scratch based on chronological transaction ledger."""
    cur.execute("SELECT ticker, transaction_type, quantity, price FROM portfolio_transactions WHERE portfolio_id = %s ORDER BY transaction_date ASC", (portfolio_id,))
    ledger = cur.fetchall()
    
    holdings = {} # ticker -> {'qty': float, 'total_cost': float}
    
    for ticker, tx_type, qty, price in ledger:
        qty, price = float(qty), float(price)
        cost = qty * price
        
        if ticker == 'ZAR_CASH':
            entry = holdings.get(ticker, {'qty': 0.0, 'total_cost': 0.0})
            if tx_type == 'BUY': entry['qty'] += qty
            elif tx_type == 'SELL': entry['qty'] -= qty
            holdings[ticker] = entry
        else:
            cash = holdings.get('ZAR_CASH', {'qty': 0.0, 'total_cost': 0.0})
            stock = holdings.get(ticker, {'qty': 0.0, 'total_cost': 0.0})
            
            if tx_type == 'BUY':
                cash['qty'] -= cost
                stock['qty'] += qty
                stock['total_cost'] += cost
            elif tx_type == 'SELL':
                # Standard JSE math: Avg buy price doesn't change on sell, total cost reduces proportionally
                if stock['qty'] > 0:
                    avg = stock['total_cost'] / stock['qty']
                    stock['qty'] -= qty
                    stock['total_cost'] = avg * stock['qty']
                cash['qty'] += cost
                
            holdings['ZAR_CASH'] = cash
            holdings[ticker] = stock

    cur.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = %s", (portfolio_id,))
    for t, d in holdings.items():
        if d['qty'] == 0: continue
        avg = (d['total_cost'] / d['qty']) if d['qty'] > 0 and t != 'ZAR_CASH' else 1.0
        cur.execute("INSERT INTO portfolio_holdings (portfolio_id, ticker, quantity, average_buy_price) VALUES (%s, %s, %s, %s)", (portfolio_id, t, d['qty'], avg))
