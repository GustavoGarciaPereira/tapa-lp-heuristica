"""Versão instrumentada do motor determinístico (cópia fiel + callback).

O algoritmo é idêntico ao de `tapa_solver_deterministico.solver.solve`; a única
diferença é que ele avisa o progresso a cada nó e respeita um pedido de parada.
Um teste compara nós/backtracks com o motor original para garantir que a
instrumentação não mudou a busca.
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from tapa_solver_deterministico.model import BLACK, WHITE, Board, Puzzle
from tapa_solver_deterministico.propagation import Contradiction, propagate
from tapa_solver_deterministico.verifier import verify


@dataclass(slots=True)
class Stats:
    nodes: int = 0
    decisions: int = 0
    backtracks: int = 0
    contradictions: int = 0
    propagated_assignments: int = 0
    propagation_rounds: int = 0
    max_depth: int = 0
    elapsed_seconds: float = 0.0
    timed_out: bool = False
    node_limit_reached: bool = False
    cancelled: bool = False
    by_rule: Counter[str] = field(default_factory=Counter)


class _Stop(Exception):
    pass


def solve_com_progresso(
    puzzle: Puzzle,
    progress: Callable[[dict], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    timeout_seconds: float | None = 120.0,
    node_limit: int | None = 1_000_000,
):
    stats = Stats()
    started = time.monotonic()

    def emit() -> None:
        if progress is not None:
            progress({
                "nodes": stats.nodes, "decisions": stats.decisions,
                "backtracks": stats.backtracks, "contradictions": stats.contradictions,
                "elapsed": time.monotonic() - started, "depth": stats.max_depth,
            })

    def check() -> None:
        if timeout_seconds is not None and time.monotonic() - started >= timeout_seconds:
            stats.timed_out = True
            raise _Stop
        if node_limit is not None and stats.nodes >= node_limit:
            stats.node_limit_reached = True
            raise _Stop
        if should_stop is not None and should_stop():
            stats.cancelled = True
            raise _Stop

    def search(board: Board, depth: int) -> Board | None:
        check()
        stats.nodes += 1
        stats.max_depth = max(stats.max_depth, depth)
        emit()
        try:
            report = propagate(board)
        except Contradiction:
            stats.contradictions += 1
            return None
        stats.propagated_assignments += report.assignments
        stats.propagation_rounds += report.iterations
        stats.by_rule.update(report.by_rule)

        if board.is_complete():
            return board if verify(board).valid else None

        index = board.unknown_indices()[0]
        stats.decisions += 1
        for color in (BLACK, WHITE):
            child = board.copy()
            child.values[index] = color
            answer = search(child, depth + 1)
            if answer is not None:
                return answer
            stats.backtracks += 1
            emit()
        return None

    board = None
    try:
        board = search(Board.initial(puzzle), 0)
    except _Stop:
        board = None
    stats.elapsed_seconds = time.monotonic() - started
    emit()

    if board is not None:
        message = "solução encontrada e verificada"
    elif stats.cancelled:
        message = "cancelado pelo usuário"
    elif stats.timed_out:
        message = "tempo limite atingido"
    elif stats.node_limit_reached:
        message = "limite de nós atingido"
    else:
        message = "a instância não possui solução"
    return board, stats, message
