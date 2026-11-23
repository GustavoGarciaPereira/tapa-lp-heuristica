"""Integração: instrumentação fiel, jobs assíncronos e histórico persistido."""
import os
import pathlib
import tempfile
import time

import pytest

os.environ.setdefault("TAPA_DATA_DIR", tempfile.mkdtemp(prefix="tapa-test-"))

from fastapi.testclient import TestClient

from tapa_solver_deterministico.solver import solve as solve_original
from tapa_lp import LPConfig, load_puzzle, solve_with_lp
from tapa_lp.instrumented import solve_com_progresso
from tapa_lp.runs import RunStore
from tapa_lp import server as srv

EXEMPLOS = pathlib.Path(__file__).resolve().parents[1] / "examples"


@pytest.mark.parametrize("path", sorted(EXEMPLOS.glob("*.txt")), ids=lambda p: p.name)
def test_instrumentado_identico_ao_original(path):
    puzzle = load_puzzle(path)
    a = solve_original(puzzle, timeout_seconds=60, node_limit=200_000)
    board, stats, _ = solve_com_progresso(puzzle, timeout_seconds=60, node_limit=200_000)
    assert (board is None) == (a.board is None)
    assert stats.nodes == a.stats.nodes
    assert stats.backtracks == a.stats.backtracks


def test_progresso_e_chamado_e_cancelamento_para():
    # tabuleiro pequeno de propósito: este teste não mede desempenho
    puzzle = load_puzzle(next(p for p in sorted(EXEMPLOS.glob("*.txt")) if p.name == "6x6_01.txt"))
    vistos = []
    solve_com_progresso(puzzle, progress=vistos.append, timeout_seconds=120)
    assert vistos and "nodes" in vistos[0]
    board, stats, message = solve_com_progresso(puzzle, should_stop=lambda: True, timeout_seconds=30)
    assert board is None and stats.cancelled and "cancelado" in message


def test_lp_aceita_progresso():
    puzzle = load_puzzle(next(p for p in sorted(EXEMPLOS.glob("*.txt")) if p.name == "6x6_01.txt"))
    vistos = []
    r = solve_with_lp(puzzle, LPConfig(), timeout_seconds=180, node_limit=500_000,
                       progress=vistos.append)
    assert r.solved, r.message
    assert vistos


@pytest.fixture()
def client(tmp_path, monkeypatch):
    store = RunStore(tmp_path / "runs.json")
    monkeypatch.setattr(srv, "store", store)
    monkeypatch.setattr(srv, "manager", srv.JobManager(store))
    return TestClient(srv.app)


def _board():
    return {
        "width": 4, "height": 4,
        "cells": [{"type": "clue" if (r, c) in {(0, 2): "1 2", (0, 3): "2", (1, 1): "7",
                                                (2, 3): "5", (3, 0): "2", (3, 1): "4"} else "unknown",
                   "label": {(0, 2): "1 2", (0, 3): "2", (1, 1): "7",
                             (2, 3): "5", (3, 0): "2", (3, 1): "4"}.get((r, c), "")}
                  for r in range(4) for c in range(4)],
    }


def _esperar(client, job_id, limite=90):
    t0 = time.time()
    while time.time() - t0 < limite:
        dado = client.get(f"/api/jobs/{job_id}").json()
        if dado["status"] in {"solved", "failed", "error", "cancelled"}:
            return dado
        time.sleep(0.1)
    raise AssertionError("job não terminou")


def test_job_roda_e_grava_resultado(client):
    corpo = dict(_board(), testName="job-1", boardId="4x4-fixture", solver="deterministico", timeoutSeconds=30)
    r = client.post("/api/jobs", json=corpo)
    assert r.status_code == 200
    dado = _esperar(client, r.json()["id"])
    assert dado["status"] == "solved"
    assert dado["result"]["verified"] is True
    assert len(dado["result"]["solution"]) == 16

    historico = client.get("/api/runs").json()
    assert len(historico["runs"]) == 1
    assert historico["runs"][0]["solver"] == "deterministico"
    assert client.get("/api/runs.csv").text.splitlines()[0].startswith("id,testName")


def test_solver_desconhecido_e_rejeitado(client):
    corpo = dict(_board(), solver="nao-existe", timeoutSeconds=5)
    assert client.post("/api/jobs", json=corpo).status_code == 400


def test_lp_recusa_tabuleiro_grande(monkeypatch, client):
    monkeypatch.setattr(srv, "MAX_BOARD_AREA", 4000)
    import tapa_lp.jobs as jobs
    monkeypatch.setattr(jobs, "MAX_LP_CELLS", 4)
    corpo = dict(_board(), solver="lp-patterns", timeoutSeconds=30)
    dado = _esperar(client, client.post("/api/jobs", json=corpo).json()["id"])
    assert dado["status"] == "error"
    assert "limite" in (dado["error"] or "")
