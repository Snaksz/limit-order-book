"""Unit tests for the limit order book."""

from __future__ import annotations

import unittest

from order_book import OrderBook, Side


class LimitOrderBookTests(unittest.TestCase):
    def test_resting_limit_orders_set_best_quotes(self) -> None:
        book = OrderBook()
        book.submit_limit(Side.BUY, 99.0, 10)
        book.submit_limit(Side.BUY, 100.0, 5)
        book.submit_limit(Side.SELL, 101.0, 7)
        book.submit_limit(Side.SELL, 102.0, 3)
        self.assertEqual(book.best_bid(), 100.0)
        self.assertEqual(book.best_ask(), 101.0)
        self.assertEqual(book.spread(), 1.0)
        self.assertEqual(book.mid_price(), 100.5)

    def test_marketable_limit_crosses_and_fills_fifo(self) -> None:
        book = OrderBook()
        a, _ = book.submit_limit(Side.SELL, 100.0, 5)
        b, _ = book.submit_limit(Side.SELL, 100.0, 5)
        _, trades = book.submit_limit(Side.BUY, 100.0, 7)
        self.assertEqual([t.quantity for t in trades], [5, 2])
        self.assertEqual(trades[0].maker_id, a)
        self.assertEqual(trades[1].maker_id, b)
        self.assertEqual(book.best_ask(), 100.0)
        self.assertEqual(book.depth(Side.SELL), [(100.0, 3)])

    def test_market_order_sweeps_multiple_levels(self) -> None:
        book = OrderBook()
        book.submit_limit(Side.SELL, 100.0, 2)
        book.submit_limit(Side.SELL, 101.0, 2)
        book.submit_limit(Side.SELL, 102.0, 2)
        _, trades, unfilled = book.submit_market(Side.BUY, 5)
        self.assertEqual(unfilled, 0)
        self.assertEqual([t.price for t in trades], [100.0, 101.0, 102.0])
        self.assertEqual(sum(t.quantity for t in trades), 5)

    def test_market_order_cancels_unfilled_remainder(self) -> None:
        book = OrderBook()
        book.submit_limit(Side.SELL, 100.0, 1)
        _, trades, unfilled = book.submit_market(Side.BUY, 5)
        self.assertEqual(sum(t.quantity for t in trades), 1)
        self.assertEqual(unfilled, 4)
        self.assertIsNone(book.best_ask())

    def test_cancel_removes_order(self) -> None:
        book = OrderBook()
        oid, _ = book.submit_limit(Side.BUY, 100.0, 10)
        self.assertTrue(book.cancel(oid))
        self.assertIsNone(book.best_bid())
        self.assertFalse(book.cancel(oid))

    def test_partial_fill_leaves_remainder_resting(self) -> None:
        book = OrderBook()
        book.submit_limit(Side.SELL, 100.0, 2)
        oid, trades = book.submit_limit(Side.BUY, 100.0, 5)
        self.assertEqual(sum(t.quantity for t in trades), 2)
        self.assertEqual(book.best_bid(), 100.0)
        self.assertEqual(book.depth(Side.BUY), [(100.0, 3)])
        self.assertTrue(book.cancel(oid))

    def test_price_time_priority_is_preserved(self) -> None:
        book = OrderBook()
        first, _ = book.submit_limit(Side.BUY, 100.0, 3)
        second, _ = book.submit_limit(Side.BUY, 100.0, 3)
        _, trades = book.submit_limit(Side.SELL, 100.0, 4)
        self.assertEqual(trades[0].maker_id, first)
        self.assertEqual(trades[0].quantity, 3)
        self.assertEqual(trades[1].maker_id, second)
        self.assertEqual(trades[1].quantity, 1)

    def test_invalid_order_rejected(self) -> None:
        book = OrderBook()
        with self.assertRaises(ValueError):
            book.submit_limit(Side.BUY, 100.0, 0)
        with self.assertRaises(ValueError):
            book.submit_limit(Side.BUY, -1.0, 1)

    def test_depth_snapshot(self) -> None:
        book = OrderBook()
        for price, qty in [(100.0, 1), (99.0, 2), (98.0, 3), (97.0, 4)]:
            book.submit_limit(Side.BUY, price, qty)
        self.assertEqual(
            book.depth(Side.BUY, levels=3),
            [(100.0, 1), (99.0, 2), (98.0, 3)],
        )


if __name__ == "__main__":
    unittest.main()
