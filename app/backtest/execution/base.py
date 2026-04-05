"""
execution/base.py — Interface abstraite de l'ExecutionHandler.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from backtest.core.events import OrderEvent


class AbstractExecutionHandler(ABC):
    """
    Transforme un OrderEvent en FillEvent.
    L'implémentation simulée exécute au close de la barre courante.
    Une implémentation live connecterait à un broker réel.
    """

    @abstractmethod
    def execute_order(self, event: OrderEvent) -> None:
        """
        Exécute l'ordre et pousse un FillEvent dans la queue.
        Le FillEvent référence l'OrderEvent (order_ref) pour la traçabilité.
        """
