"""Tests for SyntheticAdapter — determinism, structure, and data quality."""

import asyncio
from decimal import Decimal

import pytest

from alphafoundry.adapters.synthetic import SyntheticAdapter
from alphafoundry.config import SyntheticAdapterConfig
from alphafoundry.domain import OHLCBar, Quote


class TestSyntheticAdapterInstruments:
    def setup_method(self):
        self.adapter = SyntheticAdapter()

    def test_returns_instruments(self):
        instruments = self.adapter.get_instruments()
        assert len(instruments) > 0

    def test_all_instruments_have_unique_ids(self):
        instruments = self.adapter.get_instruments()
        ids = [i.instrument_id for i in instruments]
        assert len(ids) == len(set(ids))

    def test_instruments_are_nse_eq(self):
        for inst in self.adapter.get_instruments():
            assert inst.venue_id == "NSE_EQ"
            assert inst.currency == "INR"
            assert inst.is_active is True


class TestSyntheticAdapterOHLC:
    def setup_method(self):
        cfg = SyntheticAdapterConfig(seed=42, num_days=10)
        self.adapter = SyntheticAdapter(cfg)
        self.instr = self.adapter.get_instruments()[0]

    def _get_daily(self) -> list[OHLCBar]:
        bars = self.adapter._daily_bars[self.instr.instrument_id]
        return bars

    def test_correct_number_of_daily_bars(self):
        bars = self._get_daily()
        assert len(bars) == 10

    def test_ohlc_consistency(self):
        for bar in self._get_daily():
            assert bar.high >= bar.open, f"high {bar.high} < open {bar.open}"
            assert bar.high >= bar.close, f"high {bar.high} < close {bar.close}"
            assert bar.low <= bar.open, f"low {bar.low} > open {bar.open}"
            assert bar.low <= bar.close, f"low {bar.low} > close {bar.close}"
            assert bar.high >= bar.low

    def test_prices_are_positive(self):
        for bar in self._get_daily():
            assert bar.open > Decimal("0")
            assert bar.close > Decimal("0")

    def test_volume_is_positive(self):
        for bar in self._get_daily():
            assert bar.volume > 0

    def test_get_ohlc_filters_by_date(self):

        bars = self._get_daily()
        mid = bars[4].bar_open
        end = bars[-1].bar_close
        result = self.adapter.get_ohlc(self.instr.instrument_id, mid, end, "1d")
        assert len(result) > 0
        for b in result:
            assert b.bar_open >= mid

    def test_invalid_freq_raises(self):

        bars = self._get_daily()
        with pytest.raises(ValueError, match="Unsupported freq"):
            self.adapter.get_ohlc(
                self.instr.instrument_id,
                bars[0].bar_open,
                bars[-1].bar_close,
                "3m",
            )

    def test_subdivide_returns_correct_count(self):
        # 375 minutes / 5min = 75 bars
        bars = self._get_daily()
        sub = self.adapter._subdivide_daily(bars[0], interval_min=5)
        assert len(sub) == 75

    def test_1m_ohlc_via_get_ohlc(self):
        bars = self._get_daily()
        from_dt = bars[0].bar_open
        to_dt = bars[0].bar_close
        result = self.adapter.get_ohlc(self.instr.instrument_id, from_dt, to_dt, "1m")
        assert len(result) == 375  # full trading day in minutes


class TestSyntheticAdapterDeterminism:
    """Identical seed + config must produce identical output every run."""

    def _make(self, seed: int, num_days: int = 5) -> SyntheticAdapter:
        return SyntheticAdapter(SyntheticAdapterConfig(seed=seed, num_days=num_days))

    def test_same_seed_same_closes(self):
        a = self._make(seed=7)
        b = self._make(seed=7)
        inst_id = a.get_instruments()[0].instrument_id
        closes_a = [bar.close for bar in a._daily_bars[inst_id]]
        closes_b = [bar.close for bar in b._daily_bars[inst_id]]
        assert closes_a == closes_b

    def test_different_seeds_differ(self):
        a = self._make(seed=1)
        b = self._make(seed=2)
        inst_id_a = a.get_instruments()[0].instrument_id
        inst_id_b = b.get_instruments()[0].instrument_id
        closes_a = [bar.close for bar in a._daily_bars[inst_id_a]]
        closes_b = [bar.close for bar in b._daily_bars[inst_id_b]]
        # With overwhelming probability, different seeds diverge.
        assert closes_a != closes_b

    def test_seed_recorded_on_config(self):
        adapter = self._make(seed=99)
        assert adapter.cfg.seed == 99


class TestSyntheticAdapterQuotes:
    def setup_method(self):
        cfg = SyntheticAdapterConfig(seed=42, num_days=2)
        self.adapter = SyntheticAdapter(cfg)

    def test_quotes_have_positive_bid_ask(self):
        instr = self.adapter.get_instruments()[0]
        bar = self.adapter._daily_bars[instr.instrument_id][0]
        quotes = self.adapter._quotes_from_bar(instr, bar)
        assert len(quotes) == 375
        for q in quotes:
            assert q.bid_price > Decimal("0")
            assert q.ask_price >= q.bid_price

    def test_stream_quotes_async(self):
        async def _collect() -> list[Quote]:
            results: list[Quote] = []
            async for q in self.adapter.stream_quotes():
                results.append(q)
                if len(results) >= 10:
                    break
            return results

        quotes = asyncio.run(_collect())
        assert len(quotes) == 10
        for q in quotes:
            assert isinstance(q, Quote)
