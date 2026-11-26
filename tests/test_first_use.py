"""The public first-use input exercises a real compiled and exported mapping."""

import json
from pathlib import Path

from qloom.cli import main


def test_line3_first_use_exports_verified_mapping(tmp_path, capsys):
    source = Path(__file__).resolve().parents[1] / "examples/line3-routing.qasm"
    main(
        [
            "compile",
            str(source),
            "--device",
            "line-3",
            "--budget",
            "2",
            "--seed",
            "7",
            "--skip-baselines",
            "--skip-noise",
            "--out",
            str(tmp_path),
        ]
    )
    result = json.loads((tmp_path / "metadata.json").read_text())
    assert "Verified 2 candidates" in capsys.readouterr().out
    assert result["verification"]["passed"]
    assert result["verification"]["measurement_passed"]
    assert sorted(result["initial_mapping"]) == [0, 1, 2]
    assert sorted(result["final_mapping"]) == [0, 1, 2]
    assert result["measurements"] == [[0, 2], [1, 1], [2, 0]]
    assert (tmp_path / "optimized.qasm").is_file()
    assert (tmp_path / "report.json").is_file()
