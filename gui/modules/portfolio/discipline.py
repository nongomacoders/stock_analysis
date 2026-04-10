from typing import List, Dict, Any, Tuple

def calculate_portfolio_metrics(holdings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculates TPV, concentrations, and discipline status."""
    total_value = 0.0
    processed_holdings = []
    data_stale = False
    
    # First pass: Calculate individual valuations and TPV
    for h in holdings:
        ticker = h["ticker"].upper()
        # Normalize ticker for comparison (e.g., HARJO or HAR.JO)
        lookup_ticker = ticker if ".JO" in ticker or ticker == "ZAR_CASH" else f"{ticker}.JO"
        
        price = h["market_price"]
        is_stale = False
        
        if price is None:
            # Fallback to average_buy_price (already in Rands)
            price = float(h["average_buy_price"])
            is_stale = True
            if ticker != 'ZAR_CASH':
                data_stale = True
        else:
            # market_price is in cents, convert to Rands (unless it's ZAR_CASH)
            price = float(price)
            if ticker != 'ZAR_CASH':
                price = price / 100.0
        
        valuation = float(h["quantity"]) * price
        total_value += valuation
        
        # Calculate profits
        buy_price = float(h["average_buy_price"])
        profit_zar = (price - buy_price) * float(h["quantity"]) if ticker != 'ZAR_CASH' else 0.0
        profit_pct = ((price / buy_price) - 1) * 100.0 if ticker != 'ZAR_CASH' and buy_price > 0 else 0.0
        
        processed_holdings.append({
            **h,
            "valuation": valuation,
            "is_stale": is_stale,
            "effective_price": price,
            "profit_zar": profit_zar,
            "profit_pct": profit_pct
        })
    
    # Second pass: Calculate percentages and check rules
    cash_value = 0.0
    max_concentration = 0.0
    concentrated_ticker = None
    
    for h in processed_holdings:
        percent = (h["valuation"] / total_value * 100) if total_value > 0 else 0
        h["percent"] = percent
        
        if h["ticker"] == 'ZAR_CASH':
            cash_value = h["valuation"]
        else:
            if percent > max_concentration:
                max_concentration = percent
                concentrated_ticker = h["ticker"]
    
    cash_reserve_pct = (cash_value / total_value * 100) if total_value > 0 else 0
    
    # Rule 1: Cash >= 10%
    rule1_pass = cash_reserve_pct >= 10.0
    
    # Rule 2: Single stock <= 25%
    rule2_pass = max_concentration <= 25.0
    
    return {
        "TPV": total_value,
        "cash_reserve_pct": cash_reserve_pct,
        "max_concentration_pct": max_concentration,
        "concentrated_ticker": concentrated_ticker,
        "rule1_pass": rule1_pass,
        "rule2_pass": rule2_pass,
        "data_stale": data_stale,
        "holdings": processed_holdings
    }

def check_transaction_discipline(
    current_metrics: Dict[str, Any], 
    ticker: str, 
    tx_type: str,
    quantity: float, 
    price: float
) -> Tuple[bool, List[str]]:
    """Simulates a transaction and returns (is_blocked, warnings)."""
    new_tpv = current_metrics["TPV"]
    cost = quantity * price
    ticker = ticker.upper()
    
    cash_holding = next((h for h in current_metrics["holdings"] if h["ticker"] == 'ZAR_CASH'), None)
    current_cash = cash_holding["valuation"] if cash_holding else 0.0
    
    warnings = []

    if ticker == 'ZAR_CASH':
        if tx_type == 'SELL' and cost > current_cash:
            return True, [f"BLOCKER: Insufficient cash for withdrawal (Available: R{current_cash:,.2f})"]
        return False, ["Cash transaction acknowledged"]

    # --- Stock Rules ---
    stock_holding = next((h for h in current_metrics["holdings"] if h["ticker"] == ticker or h["ticker"] == f"{ticker}.JO"), None)
    current_qty = stock_holding["quantity"] if stock_holding else 0.0
    
    if tx_type == 'BUY':
        if cost > current_cash:
            return True, [f"BLOCKER: Insufficient cash (Cost: R{cost:,.2f}, Available: R{current_cash:,.2f})"]
        
        # Discipline Warnings (Soft)
        if new_tpv > 0:
            future_cash_pct = ((current_cash - cost) / new_tpv) * 100
            future_stock_val = (stock_holding["valuation"] if stock_holding else 0.0) + cost
            future_stock_pct = (future_stock_val / new_tpv) * 100
            
            if future_cash_pct < 10.0:
                warnings.append(f"BREACH: Cash reserve will drop to {future_cash_pct:.1f}% (Min: 10%)")
            if future_stock_pct > 25.0:
                warnings.append(f"BREACH: {ticker} concentration will reach {future_stock_pct:.1f}% (Max: 25%)")
    
    elif tx_type == 'SELL':
        if quantity > current_qty:
            return True, [f"BLOCKER: Insufficient shares (Owned: {current_qty:.2f})"]
        
    return False, warnings
