"""Detection package — build_scorer() is the single entry point."""

from __future__ import annotations

from typing import Any

from spyhop.detector.fresh_wallet import FreshWalletDetector
from spyhop.detector.niche_market import NicheMarketDetector
from spyhop.detector.scorer import Scorer
from spyhop.detector.size_anomaly import SizeAnomalyDetector


def build_scorer(config: dict[str, Any]) -> Scorer:
    """Create a Scorer with all detectors, configured from the app config."""
    det_cfg = config.get("detector", {})
    detectors = [
        FreshWalletDetector(det_cfg.get("fresh_wallet", {})),
        SizeAnomalyDetector(det_cfg.get("size_anomaly", {})),
        NicheMarketDetector(det_cfg.get("niche_market", {})),
    ]
    return Scorer(config.get("scorer", {}), detectors)
