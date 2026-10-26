import json

import pytest
from fastapi.testclient import TestClient
from qiskit import qasm2

from qloom.circuits import load_qasm, split_circuit
from qloom.cli import main, save_bundle
from qloom.compiler import compile_circuit
from qloom.devices import make_device
from qloom.examples import generate
from qloom.verify import verify


def test_trained_search_exact_budget_repeatable_and_export(tmp_path):
    qc = generate("random", 3, 984, 2, measured=True)
    qc.global_phase = 0.41
    kw = dict(device=make_device("line", 3), budget=3, seed=41, baselines=False, noisy=False)
    r = compile_circuit(qc, **kw)
    r2 = compile_circuit(qc, **kw)
    assert len(r["candidates"]) == 3
    assert [c["id"] for c in r["candidates"]] == [c["id"] for c in r2["candidates"]]
    assert r["model"]["training_rows"] > 0 and r["model"]["training_circuits"] > 0
    assert all(c["verification"]["passed"] for c in r["candidates"])
    save_bundle(r, tmp_path)
    meta = json.loads((tmp_path / "metadata.json").read_text())
    out = load_qasm((tmp_path / "optimized.qasm").read_text())
    out, _ = split_circuit(out)
    out.global_phase = meta["global_phase"]
    reference, _ = split_circuit(qc)
    assert verify(reference, out, meta["initial_mapping"], meta["final_mapping"])["passed"]
    assert (tmp_path / "report.json").is_file()


def test_content_addressed_cache_and_seed_strategies(tmp_path):
    qc = generate("random", 3, 864, 1)
    kw = dict(device=make_device("line", 3), budget=2, baselines=False, noisy=False, cache_dir=tmp_path)
    a = compile_circuit(qc, strategy="random", seed=5, **kw)
    assert not a["cache_hit"]
    b = compile_circuit(qc, strategy="random", seed=5, **kw)
    assert b["cache_hit"] and b["best_id"] == a["best_id"]
    c = compile_circuit(qc, strategy="heuristic", seed=5, **kw)
    assert not c["cache_hit"] and len(c["candidates"]) == 2


@pytest.mark.parametrize("budget", [0, 25, True, 2.5])
def test_invalid_budgets(budget):
    with pytest.raises(ValueError):
        compile_circuit(generate("ghz", 3), budget=budget, baselines=False, noisy=False)


def test_cli_fresh_output(tmp_path, capsys):
    source = tmp_path / "input.qasm"
    source.write_text(qasm2.dumps(generate("ghz", 3)))
    main(
        [
            "compile",
            str(source),
            "--device",
            "line-3",
            "--budget",
            "2",
            "--skip-baselines",
            "--skip-noise",
            "--out",
            str(tmp_path / "output"),
        ]
    )
    assert "Verified 2 candidates" in capsys.readouterr().out
    assert (tmp_path / "output/optimized.qasm").exists()


def test_api_real_compile_and_errors(monkeypatch):
    import qloom.server as server

    real = server.compile_circuit
    monkeypatch.setattr(
        server, "compile_circuit", lambda *a, **k: real(*a, **k, baselines=False, noisy=False)
    )
    client = TestClient(server.app)
    assert client.get("/").status_code == 200
    assert len(client.get("/api/devices").json()) == 28
    assert len(client.get("/api/examples").json()) == 5
    body = {
        "qasm": qasm2.dumps(generate("ghz", 3)),
        "device": "line-3",
        "budget": 2,
        "seed": 9,
        "strategy": "learned",
    }
    result = client.post("/api/compile", json=body)
    assert result.status_code == 200 and len(result.json()["candidates"]) == 2
    assert all(c["verification"]["passed"] for c in result.json()["candidates"])
    assert client.post("/api/compile", json={**body, "budget": 25}).status_code == 422
    assert client.post("/api/compile", json={**body, "device": "line-4"}).status_code == 422
    assert (
        client.post("/api/compile", json=body, headers={"Origin": "https://example.invalid"}).status_code
        == 403
    )
    assert client.post("/api/compile", content="x" * 130001).status_code == 413
