# limit-order-book

A price-time priority limit order book with a simple matching engine,
written in pure Python with no third-party dependencies.

The book supports:

- Resting limit orders on both sides, with FIFO priority at each price.
- Marketable limit orders that cross the spread and fill against resting
  liquidity at successively worse prices up to the limit price.
- Market orders with immediate-or-cancel semantics for any remainder that
  cannot be filled against the current book.
- Cancellation of a specific resting order by id.
- Top-of-book quotes (best bid, best ask, spread, mid price) and a depth
  snapshot of the top N levels on either side.

## Design notes

Each side of the book is stored as a dictionary mapping price to a FIFO
queue of resting orders (an `OrderedDict` keyed by order id). The best
price on each side is tracked with a heap; bid prices are stored negated
so that Python's min-heap behaves as a max-heap. Price levels that become
empty, either through full fills or through cancellations, are removed
lazily the next time they surface at the top of the heap, which keeps
cancellation O(1) in the common case.

Matching walks the opposite side one maker at a time until either the
taker is fully filled or the top of book no longer satisfies the taker's
limit price.

## Usage

```python
from order_book import OrderBook, Side

book = OrderBook()
book.submit_limit(Side.SELL, price=100.0, quantity=5)
book.submit_limit(Side.SELL, price=101.0, quantity=5)

order_id, trades = book.submit_limit(Side.BUY, price=100.5, quantity=3)
for trade in trades:
    print(trade.price, trade.quantity)

print("best bid", book.best_bid())
print("best ask", book.best_ask())
```

## Running the tests

    python3 -m unittest test_order_book -v

## Project layout

    order_book.py        Matching engine and book data structures
    test_order_book.py   Unit tests covering price-time priority,
                         cancellation, partial fills, and market orders

## License

MIT
