"""Detection package — scorer factories for each thesis."""

from __future__ import annotations

from typing import Any

from spyhop.detector.fresh_wallet import FreshWalletDetector
from spyhop.detector.niche_market import NicheMarketDetector
from spyhop.detector.scorer import Scorer
from spyhop.detector.size_anomaly import SizeAnomalyDetector


def build_scorer(config: dict[str, Any]) -> Scorer:
    """Create the insider Scorer with FreshWallet/SizeAnomaly/NicheMarket detectors.

    Reads from flat config keys (backward compat) or thesis.insider.
    """
    det_cfg = config.get("detector", {})
    detectors = [
        FreshWalletDetector(det_cfg.get("fresh_wallet", {})),
        SizeAnomalyDetector(det_cfg.get("size_anomaly", {})),
        NicheMarketDetector(det_cfg.get("niche_market", {})),
    ]
    return Scorer(config.get("scorer", {}), detectors)


def build_sports_scorer(config: dict[str, Any]) -> Scorer:
    """Create the sporty_investor Scorer with timing/entry/niche/experience detectors.

    Reads from config["thesis"]["sporty_investor"].
    """
    from spyhop.detector.entry_price import EntryPriceDetector
    from spyhop.detector.niche_nonlinear import NicheNonlinearDetector
    from spyhop.detector.timing_gate import TimingGateDetector
    from spyhop.detector.wallet_experience import WalletExperienceDetector

    thesis_cfg = config.get("thesis", {}).get("sporty_investor", {})
    det_cfg = thesis_cfg.get("detector", {})
    detectors = [
        TimingGateDetector(det_cfg.get("timing_gate", {})),
        EntryPriceDetector(det_cfg.get("entry_price", {})),
        NicheNonlinearDetector(det_cfg.get("niche_nonlinear", {})),
        WalletExperienceDetector(det_cfg.get("wallet_experience", {})),
    ]
    return Scorer(thesis_cfg.get("scorer", {}), detectors)
