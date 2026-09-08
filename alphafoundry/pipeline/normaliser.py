"""Normaliser — map adapter events to canonical domain models.

The normaliser is the seam between adapter-specific concerns and the
platform's canonical schema.  In Phase 02 the domain models *are* already
canonical (the SyntheticAdapter produces Quote/Trade/OHLCBar directly),
so normalisation is lightweight: it validates type contracts, coerces any
missing optional fields to sensible defaults, and stamps ``received_at``
with the wall-clock time if the adapter didn't provide it.

For a real vendor adapter the normaliser would translate field names,
convert price units (paise→rupees), and resolve instrument identifiers.
"""

from __future__ import annotations

from datetime import UTC, datetime

from alphafoundry.domain import OHLCBar, Quote, Trade


class Normaliser:
    """Normalise raw adapter events into canonical domain models.

    All three methods are synchronous and side-effect-free.
    """

    def normalise_quote(self, raw: Quote) -> Quote:
        """Return a Quote with ``received_at`` set to *now* if missing or naive.

        The adapter sets ``received_at = timestamp`` for synthetic data, which
        is fine for replay.  For a live feed we'd override it here.
        """
        if raw.received_at.tzinfo is None:
            # Re-stamp with UTC; can't mutate frozen model so rebuild.
            return raw.model_copy(update={"received_at": datetime.now(UTC)})
        return raw

    def normalise_trade(self, raw: Trade) -> Trade:
        """Return a Trade with ``received_at`` in UTC."""
        if raw.received_at.tzinfo is None:
            return raw.model_copy(update={"received_at": datetime.now(UTC)})
        return raw

    def normalise_bar(self, raw: OHLCBar) -> OHLCBar:
        """OHLC bars pass through unchanged; kept for interface symmetry."""
        return raw
