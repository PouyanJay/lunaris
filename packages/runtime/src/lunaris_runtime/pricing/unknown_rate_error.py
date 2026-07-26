class UnknownRateError(LookupError):
    """No rate for a (provider, model, unit) — the price book is missing an entry.

    Raised by ``PriceBook.rate``. The metering seam catches it, records the usage with ``amount``
    0, and logs the miss — so an un-priced call (a new model, a provider the book hasn't caught up
    to) never crashes a build; it just under-reports until the price book is extended.
    """
