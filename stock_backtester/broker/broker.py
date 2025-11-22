from __future__ import annotations
from dataclasses import dataclass
from typing import List

@dataclass
class Order:
    """Represents a request to trade an asset."""
    symbol: str
    quantity: float
    action: str

@dataclass
class Fill:
    """Represents a completed trade execution."""
    symbol: str
    quantity: float
    price: float
    commission: float
    action: str

class Broker:
    """
    Simulates the execution of trades, applying commissions and managing orders.
    """
    def __init__(self, commission_percentage: float = 1.0):
        self.commission_percentage = commission_percentage
        self.order_queue: List[Order] = []

    def buy(self, symbol: str, quantity: float) -> Order | None:
        if quantity > 0:
            order = Order(symbol, quantity, 'BUY')
            self.order_queue.append(order)
            return order
        return None

    def sell(self, symbol: str, quantity: float) -> Order | None:
        if quantity > 0:
            order = Order(symbol, -quantity, 'SELL')
            self.order_queue.append(order)
            return order
        return None

    def close(self, symbol: str):
        self.order_queue.append(Order(symbol, 0, 'CLOSE'))

    def get_pending_orders(self) -> List[Order]:
        orders_to_process = list(self.order_queue)
        self.order_queue.clear()
        return orders_to_process

    def execute_order(self, order: Order, fill_price: float) -> Fill | None:
        """
        Executes a single order, calculating commission and returning a Fill event.
        """
        if order.quantity == 0 and order.action != 'CLOSE':
            return None
        commission = self.commission_percentage / 100 * fill_price * abs(order.quantity)
        return Fill(
            symbol=order.symbol,
            quantity=order.quantity,
            price=fill_price,
            commission=commission,
            action=order.action
        )

