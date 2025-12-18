from dataclasses import dataclass
from datetime import datetime


@dataclass
class Event:
    id: str
    timestamp: datetime
    source: str

