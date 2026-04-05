"""
queue.py — File d'événements centrale (FIFO).

Point de passage unique pour tous les événements du moteur.
Garantit l'ordre de traitement et l'isolation entre composants.
"""

from collections import deque
from backtest.core.events import Event


class EventQueue:
    def __init__(self) -> None:
        self._queue: deque[Event] = deque()

    def put(self, event: Event) -> None:
        self._queue.append(event)

    def get(self) -> Event:
        if self._queue:
            return self._queue.popleft()
        raise IndexError("EventQueue is empty")

    def empty(self) -> bool:
        return len(self._queue) == 0

    def __len__(self) -> int:
        return len(self._queue)
