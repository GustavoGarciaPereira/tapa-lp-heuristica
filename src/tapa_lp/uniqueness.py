"""Contagem de soluções: quantas soluções o tabuleiro admite (até um limite)?

Útil porque "o solver achou uma solução" não significa "o tabuleiro é bem
formado": um Tapa com duas soluções é ambíguo, e aí dois resolvedores podem
devolver tabuleiros diferentes — ambos válidos.
"""
from __future__ import annotations

import pulp

from tapa_solver_deterministico.model import BLACK, Board, Puzzle
from tapa_solver_deterministico.patterns import patterns_for_clue, ring_indices
from tapa_solver_deterministico.verifier import verify


def count_solutions(puzzle: Puzzle, max_solutions: int = 2, time_limit: float | None = None) -> list[list[int]]:
    """Devolve até `max_solutions` soluções distintas (modelo binário exato)."""
    rows, cols = puzzle.rows, puzzle.cols
    n = rows * cols
    prob = pulp.LpProblem("tapa_unicidade", pulp.LpMinimize)
    x = {i: pulp.LpVariable(f"x{i}", cat="Binary") for i in range(n)}

    for cell, clue in puzzle.clues.items():
        slots = ring_indices(puzzle, cell)
        pats = [b for b in patterns_for_clue(clue)
                if all(b[k] == 0 for k, idx in enumerate(slots) if idx is None)]
        if not pats:
            return []
        z = [pulp.LpVariable(f"z_{cell[0]}_{cell[1]}_{p}", cat="Binary") for p in range(len(pats))]
        prob += pulp.lpSum(z) == 1
        for k, idx in enumerate(slots):
            if idx is None:
                continue
            prob += x[idx] == pulp.lpSum(z[p] for p in range(len(pats)) if pats[p][k])
        prob += x[puzzle.index(*cell)] == 0

    for r in range(rows - 1):
        for c in range(cols - 1):
            prob += (x[puzzle.index(r, c)] + x[puzzle.index(r + 1, c)]
                     + x[puzzle.index(r, c + 1)] + x[puzzle.index(r + 1, c + 1)]) <= 3

    arcs = []
    for r in range(rows):
        for c in range(cols):
            u = puzzle.index(r, c)
            for dr, dc in ((1, 0), (0, 1)):
                if puzzle.in_bounds(r + dr, c + dc):
                    v = puzzle.index(r + dr, c + dc)
                    arcs += [(u, v), (v, u)]
    f = [pulp.LpVariable(f"f{k}", lowBound=0, upBound=n) for k in range(len(arcs))]
    y = {i: pulp.LpVariable(f"y{i}", cat="Binary") for i in range(n)}
    prob += pulp.lpSum(y.values()) == 1
    entrada = {i: [] for i in range(n)}
    saida = {i: [] for i in range(n)}
    for k, (u, v) in enumerate(arcs):
        prob += f[k] <= n * x[u]
        prob += f[k] <= n * x[v]
        saida[u].append(f[k])
        entrada[v].append(f[k])
    for i in range(n):
        s = pulp.LpVariable(f"s{i}", lowBound=0, upBound=n)
        prob += s <= n * y[i]
        prob += pulp.lpSum(entrada[i]) + s - pulp.lpSum(saida[i]) == x[i]

    prob += 0
    solver = pulp.PULP_CBC_CMD(msg=False) if time_limit is None else pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)
    encontradas: list[list[int]] = []
    for _ in range(max_solutions):
        if pulp.LpStatus[prob.solve(solver)] != "Optimal":
            break
        sol = [int(round(x[i].value())) for i in range(n)]
        if not verify(Board(puzzle, sol)).valid:
            raise RuntimeError("o modelo de unicidade gerou uma solução inválida")
        encontradas.append(sol)
        prob += pulp.lpSum((1 - x[i]) if sol[i] else x[i] for i in range(n)) >= 1
    return encontradas
