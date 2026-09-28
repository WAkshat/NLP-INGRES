"""INGRES-Bench checks: noise generator + full QC on the committed benchmark file."""
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_benchmark import schema_refs, typo  # noqa: E402

BENCH = ROOT / "data/benchmark/ingres_bench_v1.jsonl"


def test_typo_always_changes_name():
    rng = random.Random(0)
    for name in ["Jind", "Ludhiana-1", "Bhagwanpur", "Leh", "Gaya"]:
        for _ in range(50):
            assert typo(name, rng) != name


def test_schema_refs():
    schema = {"tables": [{"name": "states", "columns": [{"name": "state_name"}, {"name": "state_id"}]},
                         {"name": "districts", "columns": [{"name": "district_name"}]}]}
    assert schema_refs("SELECT state_name FROM states", schema) == (["states"], ["state_name"])


@pytest.mark.skipif(not (BENCH.exists() and (ROOT / "data/processed/ingres.db").exists()), reason="benchmark or db missing")
def test_benchmark_qc_passes():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/qc_benchmark.py")], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stdout[-2000:]
