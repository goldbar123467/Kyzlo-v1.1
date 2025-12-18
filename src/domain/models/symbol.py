from dataclasses import dataclass


@dataclass(frozen=True)
class Symbol:
    """Lightweight symbol metadata."""

    name: str
    base_asset: str
    quote_asset: str
    is_perp: bool = False

    def to_pair(self) -> str:
        return f"{self.base_asset}/{self.quote_asset}"

