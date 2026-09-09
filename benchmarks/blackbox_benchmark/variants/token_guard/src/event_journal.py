"""Event sourcing journal with deterministic replay.

Records all state-mutating events with timestamps and sequence numbers.
Provides replay capability to reconstruct state from the event log.
Events can be serialized to/from JSON for persistence.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Event:
    """A single immutable event in the journal."""
    event_id: str
    event_type: str
    timestamp: float
    sequence: int
    payload: Dict[str, Any]
    source_node: str = ""
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Event":
        return cls(**d)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> "Event":
        return cls.from_dict(json.loads(s))


class EventJournal:
    """Append-only event journal with replay support."""

    def __init__(self) -> None:
        self.events: List[Event] = []
        self._sequence = 0
        self._handlers: Dict[str, List[Callable[[Event], None]]] = {}

    def register_handler(self, event_type: str, handler: Callable[[Event], None]) -> None:
        """Register a handler to be called during replay for *event_type*."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def append(self, event_type: str, payload: Dict[str, Any],
               source_node: str = "", timestamp: Optional[float] = None) -> Event:
        """Create and append a new event.  Returns the event."""
        self._sequence += 1
        evt = Event(
            event_id=f"EVT-{self._sequence:08d}",
            event_type=event_type,
            timestamp=timestamp if timestamp is not None else time.time(),
            sequence=self._sequence,
            payload=payload,
            source_node=source_node,
        )
        # Compute checksum from serialized form
        import hashlib
        evt.checksum = hashlib.sha256(evt.to_json().encode()).hexdigest()[:16]

        self.events.append(evt)
        return evt

    def replay(self, target_sequence: Optional[int] = None) -> int:
        """Replay events in order, calling registered handlers.

        If *target_sequence* is given, replay only up to that sequence.

        BUG #6: Events are sorted by timestamp instead of sequence number.
        When multiple events share the same millisecond-granularity timestamp,
        Python's sort (which is stable) preserves insertion order — BUT if
        events were received out of order from different nodes, they may have
        been inserted in the wrong sequence order.  The correct sort key is
        the monotonic sequence number.
        """
        events_to_replay = list(self.events)

        if target_sequence is not None:
            events_to_replay = [e for e in events_to_replay if e.sequence <= target_sequence]

        events_to_replay.sort(key=lambda e: e.sequence)

        replayed = 0
        for evt in events_to_replay:
            handlers = self._handlers.get(evt.event_type, [])
            for handler in handlers:
                handler(evt)
            replayed += 1

        return replayed

    def serialize(self) -> str:
        """Serialize entire journal to JSON."""
        return json.dumps([e.to_dict() for e in self.events], indent=2)

    def deserialize(self, data: str) -> None:
        """Load journal from serialized JSON."""
        entries = json.loads(data)
        self.events = [Event.from_dict(e) for e in entries]
        if self.events:
            self._sequence = max(e.sequence for e in self.events)

    def compact(self, keep_last_n: int = 1000) -> int:
        """Remove old events, keeping only the last *keep_last_n*.

        Returns number of events removed.
        """
        if len(self.events) <= keep_last_n:
            return 0
        removed = len(self.events) - keep_last_n
        self.events = self.events[-keep_last_n:]
        return removed

    def find_events(self, event_type: Optional[str] = None,
                    source_node: Optional[str] = None,
                    min_sequence: Optional[int] = None,
                    max_sequence: Optional[int] = None) -> List[Event]:
        """Query events matching the given filters."""
        result: List[Event] = []
        for evt in self.events:
            if event_type and evt.event_type != event_type:
                continue
            if source_node and evt.source_node != source_node:
                continue
            if min_sequence is not None and evt.sequence < min_sequence:
                continue
            if max_sequence is not None and evt.sequence > max_sequence:
                continue
            result.append(evt)
        return result
