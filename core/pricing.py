"""Model price table (USD per 1M tokens), loaded from `config/prices.yaml`.

Prices change often, so none are hard-coded: enter the ones you use in the YAML file
(Settings page editing comes in M2). Unknown models simply have no cost.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ModelPrice(BaseModel):
    """Price of one model in USD per 1M tokens."""

    input_per_1m: float = Field(ge=0)
    output_per_1m: float = Field(ge=0)
    cached_input_per_1m: float | None = Field(default=None, ge=0)


class PriceTable(BaseModel):
    """Prices keyed by model name (without provider prefix)."""

    models: dict[str, ModelPrice] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> PriceTable:
        """Load from YAML; a missing or empty file gives an empty table."""
        if not path.is_file():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.model_validate({"models": data.get("models") or {}})

    def cost(
        self, model: str | None, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0
    ) -> float | None:
        """Cost in USD, or None when the model has no price entry."""
        if not model:
            return None
        price = self.models.get(model.split(":", 1)[-1])
        if price is None:
            return None
        cached_rate = price.cached_input_per_1m if price.cached_input_per_1m is not None else price.input_per_1m
        uncached = max(input_tokens - cached_input_tokens, 0)
        return (
            uncached * price.input_per_1m + cached_input_tokens * cached_rate + output_tokens * price.output_per_1m
        ) / 1_000_000
