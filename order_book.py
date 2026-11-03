"""Price-time priority limit order book with a simple matching engine.

The book supports limit orders, marketable limits that cross the spread,
immediate-or-cancel market orders, and cancellations. Orders at the same
price are matched in FIFO (arrival) order. Resting orders are indexed by
id for O(log n) cancellation via lazy price-level cleanup.

This module has no third-party dependencies. It is designed for study,
testing, and backtesting, not for production throughput.
"""

from __future__ import annotations

import heapq
import itertools
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Order:
    order_id: int
    side: Side
    price: float
    quantity: int
    time: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.price <= 0:
            raise ValueError("price must be positive")


@dataclass
class Trade:
    maker_id: int
    taker_id: int
    price: float
    quantity: int
    time: int


@dataclass
class _Level:
    """FIFO queue of resting orders at one price."""
    price: float
    orders: "OrderedDict[int, Order]" = field(default_factory=OrderedDict)
    total_quantity: int = 0

    def add(self, order: Order) -> None:
        self.orders[order.order_id] = order
        self.total_quantity += order.quantity

    def pop_front(self) -> Order:
        _, order = self.orders.popitem(last=False)
        self.total_quantity -= order.quantity
        return order

    def peek_front(self) -> Order:
        order_id = next(iter(self.orders))
        return self.orders[order_id]

    def remove(self, order_id: int) -> Optional[Order]:
        order = self.orders.pop(order_id, None)
        if order is not None:
            self.total_quantity -= order.quantity
        return order

    def is_empty(self) -> bool:
        return not self.orders


class OrderBook:
    """Limit order book with a price-time priority matching engine.

    Best bid is tracked as a max-heap (negated prices) and best ask as a
    min-heap. Empty price levels are removed lazily when they surface at
    the top of either heap.
    """

    def __init__(self) -> None:
        self._bid_levels: Dict[float, _Level] = {}
        self._ask_levels: Dict[float, _Level] = {}
        self._bid_heap: List[float] = []
        self._ask_heap: List[float] = []
        self._orders_index: Dict[int, Tuple[Side, float]] = {}
        self._order_id_seq = itertools.count(1)
        self._time_seq = itertools.count(1)

    # ---- public API -----------------------------------------------------

    def submit_limit(self, side: Side, price: float, quantity: int) -> Tuple[int, List[Trade]]:
        """Submit a limit order. Returns (order_id, trades_filled)."""
        order = Order(
            order_id=next(self._order_id_seq),
            side=side,
            price=price,
            quantity=quantity,
            time=next(self._time_seq),
        )
        trades = self._match(order)
        if order.quantity > 0:
            self._rest(order)
        return order.order_id, trades

    def submit_market(self, side: Side, quantity: int) -> Tuple[int, List[Trade], int]:
        """Submit a market order. Returns (order_id, trades, unfilled_qty).

        A market order sweeps the opposite side at any price and cancels any
        unfilled remainder (immediate-or-cancel semantics).
        """
        sentinel_price = float("inf") if side is Side.BUY else 1e-12
        order = Order(
            order_id=next(self._order_id_seq),
            side=side,
            price=sentinel_price,
            quantity=quantity,
            time=next(self._time_seq),
        )
        trades = self._match(order)
        return order.order_id, trades, order.quantity

    def cancel(self, order_id: int) -> bool:
        """Cancel a resting order. Returns True if an order was removed."""
        entry = self._orders_index.pop(order_id, None)
        if entry is None:
            return False
        side, price = entry
        levels = self._bid_levels if side is Side.BUY else self._ask_levels
        level = levels.get(price)
        if level is None:
            return False
        level.remove(order_id)
        if level.is_empty():
            del levels[price]
        return True

    def best_bid(self) -> Optional[float]:
        return self._top_price(self._bid_heap, self._bid_levels, bid=True)

    def best_ask(self) -> Optional[float]:
        return self._top_price(self._ask_heap, self._ask_levels, bid=False)

    def spread(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return ba - bb

    def mid_price(self) -> Optional[float]:
        bb, ba = self.best_bid(), self.best_ask()
        if bb is None or ba is None:
            return None
        return (bb + ba) / 2.0

    def depth(self, side: Side, levels: int = 5) -> List[Tuple[float, int]]:
        """Return the top `levels` price levels on `side` as (price, qty)."""
        if side is Side.BUY:
            heap = sorted(self._bid_levels.keys(), reverse=True)
            level_map = self._bid_levels
        else:
            heap = sorted(self._ask_levels.keys())
            level_map = self._ask_levels
        out: List[Tuple[float, int]] = []
        for price in heap[:levels]:
            out.append((price, level_map[price].total_quantity))
        return out

    # ---- internals ------------------------------------------------------

    def _top_price(
        self, heap: List[float], levels: Dict[float, _Level], bid: bool
    ) -> Optional[float]:
        while heap:
            raw = heap[0]
            price = -raw if bid else raw
            if price in levels and not levels[price].is_empty():
                return price
            heapq.heappop(heap)
        return None

    def _match(self, taker: Order) -> List[Trade]:
        trades: List[Trade] = []
        if taker.side is Side.BUY:
            opposite_levels = self._ask_levels
            opposite_heap = self._ask_heap
            price_ok = lambda best: best <= taker.price  # noqa: E731
            bid = False
        else:
            opposite_levels = self._bid_levels
            opposite_heap = self._bid_heap
            price_ok = lambda best: best >= taker.price  # noqa: E731
            bid = True

        while taker.quantity > 0:
            best = self._top_price(opposite_heap, opposite_levels, bid=bid)
            if best is None or not price_ok(best):
                break
            level = opposite_levels[best]
            maker = level.peek_front()
            fill_qty = min(taker.quantity, maker.quantity)
            trades.append(
                Trade(
                    maker_id=maker.order_id,
                    taker_id=taker.order_id,
                    price=maker.price,
                    quantity=fill_qty,
                    time=next(self._time_seq),
                )
            )
            taker.quantity -= fill_qty
            maker.quantity -= fill_qty
            level.total_quantity -= fill_qty
            if maker.quantity == 0:
                level.orders.popitem(last=False)
                self._orders_index.pop(maker.order_id, None)
                if level.is_empty():
                    del opposite_levels[best]
        return trades

    def _rest(self, order: Order) -> None:
        if order.side is Side.BUY:
            level = self._bid_levels.get(order.price)
            if level is None:
                level = _Level(order.price)
                self._bid_levels[order.price] = level
                heapq.heappush(self._bid_heap, -order.price)
        else:
            level = self._ask_levels.get(order.price)
            if level is None:
                level = _Level(order.price)
                self._ask_levels[order.price] = level
                heapq.heappush(self._ask_heap, order.price)
        level.add(order)
        self._orders_index[order.order_id] = (order.side, order.price)
