"""Heurística de Programação Linear para o resolvedor determinístico de Tapa."""

from .lp_model import TapaRelaxation, LPStats
from .solver_lp import LPConfig, solve_with_lp
from .io_puzzles import load_puzzle, render_solution
from .uniqueness import count_solutions

__all__ = ["TapaRelaxation", "LPStats", "LPConfig", "solve_with_lp",
           "load_puzzle", "render_solution", "count_solutions"]
