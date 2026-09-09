"""Price-time priority order matching engine.

Implements a limit order book with:
  - Price-time priority matching
  - Iceberg (hidden quantity) orders
  - Fill-or-Kill (FOK) and Immediate-or-Cancel (IOC) order types
  - Trade execution with maker/taker semantics
"""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    LIMIT = "LIMIT"
    ICEBERG = "ICEBERG"
    FOK = "FOK"        # Fill-or-Kill
    IOC = "IOC"        # Immediate-or-Cancel


@dataclass
class Order:
    order_id: str
    side: Side
    price: float             # BUG #4: Using float for price instead of int cents
    quantity: int
    order_type: OrderType = OrderType.LIMIT
    display_qty: int = 0     # For ICEBERG: visible quantity
    total_qty: int = 0       # For ICEBERG: original full quantity
    filled_qty: int = 0
    timestamp: float = field(default_factory=time.time)
    is_active: bool = True

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled_qty

    @property
    def visible_quantity(self) -> int:
        if self.order_type == OrderType.ICEBERG:
            return min(self.display_qty, self.remaining)
        return self.remaining


@dataclass
class Trade:
    trade_id: str
    buy_order_id: str
    sell_order_id: str
    price: float
    quantity: int
    timestamp: float


class OrderBook:
    """Limit order book for a single symbol with price-time priority."""

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.bids: List[Tuple[float, float, Order]] = []  # max-heap: (-price, time, order)
        self.asks: List[Tuple[float, float, Order]] = []  # min-heap: (price, time, order)
        self.orders: Dict[str, Order] = {}
        self.trades: List[Trade] = []
        self._trade_counter = 0

    def submit_order(self, order: Order) -> List[Trade]:
        """Submit an order and attempt matching.  Returns list of trades."""
        if order.order_type == OrderType.ICEBERG and order.display_qty <= 0:
            raise ValueError("Iceberg orders must have display_qty > 0")

        if order.order_type == OrderType.FOK:
            return self._handle_fok(order)
        elif order.order_type == OrderType.IOC:
            return self._handle_ioc(order)
        else:
            return self._match_and_insert(order)

    def _handle_fok(self, order: Order) -> List[Trade]:
        """Fill-or-Kill: fill entirely or reject."""
        available = self._available_liquidity(order)
        if available < order.quantity:
            order.is_active = False
            return []
        return self._match_and_insert(order)

    def _handle_ioc(self, order: Order) -> List[Trade]:
        """Immediate-or-Cancel: fill what's available, cancel the rest."""
        trades = self._match_and_insert(order)
        if order.remaining > 0:
            order.is_active = False
            if order.order_id in self.orders:
                del self.orders[order.order_id]
        return trades

    def _available_liquidity(self, order: Order) -> int:
        """Check available matchable quantity without executing."""
        total = 0
        if order.side == Side.BUY:
            for price, _, ask_order in sorted(self.asks):
                if price > order.price:
                    break
                if ask_order.is_active:
                    total += ask_order.remaining
        else:
            for neg_price, _, bid_order in sorted(self.bids):
                if -neg_price < order.price:
                    break
                if bid_order.is_active:
                    total += bid_order.remaining
        return total

    def _match_and_insert(self, order: Order) -> List[Trade]:
        """Core matching logic with price-time priority."""
        trades: List[Trade] = []

        if order.side == Side.BUY:
            trades = self._match_buy(order)
        else:
            trades = self._match_sell(order)

        # Insert remainder into book if still active
        if order.remaining > 0 and order.is_active:
            self.orders[order.order_id] = order
            if order.side == Side.BUY:
                heapq.heappush(self.bids, (-order.price, order.timestamp, order))
            else:
                heapq.heappush(self.asks, (order.price, order.timestamp, order))

        return trades

    def _match_buy(self, buy_order: Order) -> List[Trade]:
        """Match a buy order against the ask side."""
        trades: List[Trade] = []

        while self.asks and buy_order.remaining > 0:
            best_ask_price, _, best_ask = self.asks[0]

            if not best_ask.is_active:
                heapq.heappop(self.asks)
                continue

            # BUG #4: Float comparison — prices like 10.10 and 10.1 may not
            # compare correctly due to IEEE 754 representation.
            if best_ask_price > buy_order.price:
                break

            fill_qty = min(buy_order.remaining, best_ask.visible_quantity)
            if fill_qty <= 0:
                heapq.heappop(self.asks)
                continue

            self._trade_counter += 1
            trade = Trade(
                trade_id=f"T-{self._trade_counter:06d}",
                buy_order_id=buy_order.order_id,
                sell_order_id=best_ask.order_id,
                price=best_ask_price,
                quantity=fill_qty,
                timestamp=time.time(),
            )
            trades.append(trade)
            self.trades.append(trade)

            buy_order.filled_qty += fill_qty
            best_ask.filled_qty += fill_qty

            # BUG #5 (ICEBERG): After filling the visible quantity of an
            # iceberg order, we should "refresh" its visible quantity from
            # the hidden reserve.  But here we remove it without refreshing.
            if best_ask.remaining <= 0:
                best_ask.is_active = False
                heapq.heappop(self.asks)
            elif best_ask.order_type == OrderType.ICEBERG:
                # Should re-push with refreshed display_qty, but instead
                # we just pop it and discard the hidden quantity.
                heapq.heappop(self.asks)
                # BUG: iceberg not re-inserted — hidden liquidity is lost
            else:
                if best_ask.visible_quantity <= 0:
                    heapq.heappop(self.asks)

        return trades

    def _match_sell(self, sell_order: Order) -> List[Trade]:
        """Match a sell order against the bid side."""
        trades: List[Trade] = []

        while self.bids and sell_order.remaining > 0:
            neg_price, _, best_bid = self.bids[0]
            best_bid_price = -neg_price

            if not best_bid.is_active:
                heapq.heappop(self.bids)
                continue

            if best_bid_price < sell_order.price:
                break

            fill_qty = min(sell_order.remaining, best_bid.visible_quantity)
            if fill_qty <= 0:
                heapq.heappop(self.bids)
                continue

            self._trade_counter += 1
            trade = Trade(
                trade_id=f"T-{self._trade_counter:06d}",
                buy_order_id=best_bid.order_id,
                sell_order_id=sell_order.order_id,
                price=best_bid_price,
                quantity=fill_qty,
                timestamp=time.time(),
            )
            trades.append(trade)
            self.trades.append(trade)

            sell_order.filled_qty += fill_qty
            best_bid.filled_qty += fill_qty

            if best_bid.remaining <= 0:
                best_bid.is_active = False
                heapq.heappop(self.bids)
            elif best_bid.order_type == OrderType.ICEBERG:
                heapq.heappop(self.bids)
                # BUG: same iceberg issue on bid side
            else:
                if best_bid.visible_quantity <= 0:
                    heapq.heappop(self.bids)

        return trades

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an active order.  Returns True if found and cancelled."""
        order = self.orders.get(order_id)
        if order and order.is_active:
            order.is_active = False
            del self.orders[order_id]
            return True
        return False

    def best_bid(self) -> Optional[float]:
        while self.bids:
            neg_p, _, o = self.bids[0]
            if o.is_active and o.remaining > 0:
                return -neg_p
            heapq.heappop(self.bids)
        return None

    def best_ask(self) -> Optional[float]:
        while self.asks:
            p, _, o = self.asks[0]
            if o.is_active and o.remaining > 0:
                return p
            heapq.heappop(self.asks)
        return None

    def spread(self) -> Optional[float]:
        bb = self.best_bid()
        ba = self.best_ask()
        if bb is not None and ba is not None:
            return ba - bb
        return None

    def depth(self, levels: int = 5) -> Dict[str, List[Tuple[float, int]]]:
        """Return top *levels* of bid/ask depth."""
        bid_depth: Dict[float, int] = {}
        for neg_p, _, o in self.bids:
            if o.is_active and o.remaining > 0:
                p = -neg_p
                bid_depth[p] = bid_depth.get(p, 0) + o.visible_quantity
        ask_depth: Dict[float, int] = {}
        for p, _, o in self.asks:
            if o.is_active and o.remaining > 0:
                ask_depth[p] = ask_depth.get(p, 0) + o.visible_quantity

        return {
            "bids": sorted(bid_depth.items(), reverse=True)[:levels],
            "asks": sorted(ask_depth.items())[:levels],
        }
