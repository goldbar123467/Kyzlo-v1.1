from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List
from collections import defaultdict
import hashlib


@dataclass
class FillFingerprint:
    venue_fill_id: str
    order_id: str
    timestamp: datetime
    qty: Decimal
    price: Decimal

    def hash(self) -> str:
        content = f"{self.venue_fill_id}:{self.order_id}:{self.timestamp.isoformat()}:{self.qty}:{self.price}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class FillSequencer:
    """Handles out-of-order fills."""

    def __init__(self, max_wait_seconds: float = 5.0):
        self.max_wait_seconds = max_wait_seconds
        self._pending_fills: Dict[str, List] = defaultdict(list)
        self._expected_seq: Dict[str, int] = {}
        self._seen_hashes: set = set()

    def receive_fill(self, fill: "ExecutionReport") -> List["ExecutionReport"]:
        fingerprint = FillFingerprint(
            venue_fill_id=fill.venue_fill_id,
            order_id=fill.order_id,
            timestamp=fill.timestamp,
            qty=fill.filled_qty,
            price=fill.avg_fill_price or Decimal("0"),
        )
        fill_hash = fingerprint.hash()
        if fill_hash in self._seen_hashes:
            return []

        self._seen_hashes.add(fill_hash)
        order_id = fill.order_id
        if order_id not in self._expected_seq:
            self._expected_seq[order_id] = 1

        self._pending_fills[order_id].append(fill)
        return self._release_ordered_fills(order_id)

    def _release_ordered_fills(self, order_id: str) -> List["ExecutionReport"]:
        ready = []
        pending = self._pending_fills[order_id]
        expected = self._expected_seq[order_id]

        pending.sort(key=lambda f: f.sequence_number)
        while pending:
            next_fill = pending[0]
            if next_fill.sequence_number == expected:
                ready.append(pending.pop(0))
                expected += 1
                self._expected_seq[order_id] = expected
            elif next_fill.sequence_number < expected:
                pending.pop(0)
            else:
                oldest = min(pending, key=lambda f: f.timestamp)
                age = (datetime.utcnow() - oldest.timestamp).total_seconds()
                if age > self.max_wait_seconds:
                    ready.extend(pending)
                    pending.clear()
                else:
                    break
        return ready

