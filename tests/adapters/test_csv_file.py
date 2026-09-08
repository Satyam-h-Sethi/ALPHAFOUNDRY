"""Tests for CsvFileAdapter."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alphafoundry.adapters.csv_file import CsvAdapterConfig, CsvFileAdapter

_FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestCsvFileAdapter:
    def test_stream_quotes_from_csv(self):
        cfg = CsvAdapterConfig(quotes_path=str(_FIXTURES / "sample_quotes.csv"))
        adapter = CsvFileAdapter(cfg)

        async def _collect():
            return [q async for q in adapter.stream_quotes()]

        quotes = asyncio.run(_collect())
        assert len(quotes) == 3
        # Check that the domain models are valid Pydantic instances
        from alphafoundry.domain import Quote

        assert all(isinstance(q, Quote) for q in quotes)
        # Prices are Decimal
        from decimal import Decimal

        assert isinstance(quotes[0].bid_price, Decimal)

    def test_stream_trades_from_csv(self):
        cfg = CsvAdapterConfig(trades_path=str(_FIXTURES / "sample_trades.csv"))
        adapter = CsvFileAdapter(cfg)

        async def _collect():
            return [t async for t in adapter.stream_trades()]

        trades = asyncio.run(_collect())
        assert len(trades) == 3
        from alphafoundry.domain import Trade

        assert all(isinstance(t, Trade) for t in trades)

    def test_stream_quotes_none_path_yields_nothing(self):
        cfg = CsvAdapterConfig(quotes_path=None)
        adapter = CsvFileAdapter(cfg)

        async def _collect():
            return [q async for q in adapter.stream_quotes()]

        quotes = asyncio.run(_collect())
        assert quotes == []

    def test_stream_trades_none_path_yields_nothing(self):
        cfg = CsvAdapterConfig(trades_path=None)
        adapter = CsvFileAdapter(cfg)

        async def _collect():
            return [t async for t in adapter.stream_trades()]

        trades = asyncio.run(_collect())
        assert trades == []

    def test_get_instruments_returns_injected(self):
        from decimal import Decimal
        from uuid import uuid4

        from alphafoundry.domain.enums import InstrumentType
        from alphafoundry.domain.instruments import Instrument

        instr = Instrument(
            instrument_id=uuid4(),
            symbol="CSV_INSTR",
            venue_id="NSE_EQ",
            instrument_type=InstrumentType.EQ,
            lot_size=1,
            tick_size=Decimal("0.05"),
        )
        cfg = CsvAdapterConfig(instruments=[instr])
        adapter = CsvFileAdapter(cfg)
        assert adapter.get_instruments() == [instr]

    def test_csv_replay_through_pipeline(self):
        """CSV quotes feed through the full DataPipeline without error."""
        from alphafoundry.pipeline import DataPipeline, IngestOutcome, PipelineConfig

        cfg = CsvAdapterConfig(quotes_path=str(_FIXTURES / "sample_quotes.csv"))
        adapter = CsvFileAdapter(cfg)
        pipeline = DataPipeline(PipelineConfig(db_path=":memory:", adapter_id="csv_test"))

        async def _run():
            return await pipeline.run_quotes(adapter.stream_quotes())

        counts = asyncio.run(_run())
        total = sum(counts.values())
        # All 3 fixture rows should be processed (ACCEPTED or another outcome).
        assert total == 3
        # The fixture data is valid; all should be ACCEPTED.
        assert counts[IngestOutcome.ACCEPTED.value] == 3
