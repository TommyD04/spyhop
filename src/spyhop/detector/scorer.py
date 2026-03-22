"""Composite scorer — multiplicative model mapped to 0-10 scale.

Scoring math (from SYNTHESIS §1.2):
  product = fresh_mult * size_mult * niche_mult
  composite = log10(product) * normalizer   (clamped to 0-10)

The normalizer is computed from the maximum possible product so that
all-max-signals = 10.0. Single signal scores ~2-4, two signals ~5-7,
three signals ~7-10.
"""

from __future__ import annotations

import math
from functools import reduce
from operator import mul
from typing import Any

from spyhop.detector.base import DetectionContext, ScoreResult


class Scorer:
    """Runs all detectors and produces a composite 0-10 score."""

    def __init__(self, config: dict[str, Any], detectors: list) -> None:
        self._detectors = detectors
        self._alert = config.get("alert_threshold", 7)
        self._critical = config.get("critical_threshold", 9)

        # Compute normalizer from max possible multipliers
        max_product = reduce(mul, (d.max_multiplier for d in detectors), 1.0)
        if max_product > 1.0:
            self._normalizer = 10.0 / math.log10(max_product)
        else:
            self._normalizer = 10.0

    def score(self, context: DetectionContext) -> ScoreResult:
        """Run all detectors and compute composite score."""
        results = [d.evaluate(context) for d in self._detectors]

        product = reduce(mul, (r.multiplier for r in results), 1.0)

        if product <= 1.0:
            composite = 0.0
        else:
            composite = min(10.0, math.log10(product) * self._normalizer)

        return ScoreResult(
            composite=round(composite, 1),
            signals=results,
            alert=composite >= self._alert,
            critical=composite >= self._critical,
        )
