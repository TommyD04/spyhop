"""Tests for RTDS ingestor deduplication filter."""

from __future__ import annotations

from spyhop.ingestor.rtds import _Deduplicator


def _trade(tx_hash: str = "0xabc", wallet: str = "0x123", asset_id: str = "a1"):
    """Build a minimal trade dict with dedup-relevant fields."""
    return {"tx_hash": tx_hash, "wallet": wallet, "asset_id": asset_id}


class TestDeduplicator:
    def test_first_trade_passes(self):
        d = _Deduplicator()
        assert not d.is_duplicate(_trade())

    def test_second_identical_trade_blocked(self):
        d = _Deduplicator()
        assert not d.is_duplicate(_trade())
        assert d.is_duplicate(_trade())

    def test_different_tx_hash_passes(self):
        d = _Deduplicator()
        assert not d.is_duplicate(_trade(tx_hash="0xabc"))
        assert not d.is_duplicate(_trade(tx_hash="0xdef"))

    def test_same_tx_different_wallet_passes(self):
        """CLOB batch settlement: same tx_hash, different wallets are distinct."""
        d = _Deduplicator()
        assert not d.is_duplicate(_trade(tx_hash="0xabc", wallet="0x111"))
        assert not d.is_duplicate(_trade(tx_hash="0xabc", wallet="0x222"))

    def test_same_tx_different_asset_passes(self):
        """Same tx, same wallet, different asset — distinct fill."""
        d = _Deduplicator()
        assert not d.is_duplicate(_trade(asset_id="a1"))
        assert not d.is_duplicate(_trade(asset_id="a2"))

    def test_empty_tx_hash_never_deduped(self):
        """Trades with missing tx_hash should pass through (safety valve)."""
        d = _Deduplicator()
        assert not d.is_duplicate(_trade(tx_hash=""))
        assert not d.is_duplicate(_trade(tx_hash=""))

    def test_resets_at_max_size(self):
        d = _Deduplicator(max_size=3)
        assert not d.is_duplicate(_trade(tx_hash="0x1"))
        assert not d.is_duplicate(_trade(tx_hash="0x2"))
        assert not d.is_duplicate(_trade(tx_hash="0x3"))
        # Set is full (3/3). Next new trade triggers reset.
        assert not d.is_duplicate(_trade(tx_hash="0x4"))
        # After reset, a previously-seen trade passes again (expected)
        assert not d.is_duplicate(_trade(tx_hash="0x1"))

    def test_counter_tracks_dupes(self):
        d = _Deduplicator()
        assert d._dupes_blocked == 0
        d.is_duplicate(_trade())
        d.is_duplicate(_trade())
        d.is_duplicate(_trade())
        assert d._dupes_blocked == 2
