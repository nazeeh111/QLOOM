# Development and release checks

The core and all inference are CPU-compatible. Use Python 3.11–3.13. The measured research run used Python3.12.13 on an ARM Mac. Create a virtual environment, then install `.[dev,research]`. For the measured package versions, use `pip install -r requirements-research-py312.lock` on compatible Python3.12 before `pip install --no-deps -e .`; the lock records the observed research environment, not universal platform wheel availability.

Run `python -m pytest -q` for core, adversarial, export, model, CLI and API checks. Eight external compiler regressions are opt-in: `QLOOM_TEST_OPTIONAL_BASELINES=1 python -m pytest tests/test_baselines.py -q`. `python scripts/check_baselines.py` performs all six real compiler comparisons and exact density-matrix simulation on a small measured circuit. A missing optional dependency or a timeout is visible; it is not silently counted as a passing baseline. The CI workflow checks core wheels across three Python versions and optional compiler/noise behavior on Python3.12.

`ruff check src tests scripts` and `ruff format --check src tests scripts` check code quality and formatting. `python -m build` builds a wheel and source distribution. The wheel includes the safe JSON model, actual recorded demo, benchmark summary, and all static Studio assets.

The local server binds only to127.0.0.1, rejects cross-origin browser requests, bounds input sizes and parameters, and allows one compilation at a time. It is a desktop research server, not a hardened public multi-user deployment. Its static root contains only packaged frontend files. The circuit importer rejects filesystem includes beyond the standard qelib1.inc. No model credentials or quantum cloud accounts are needed.

QMAP/BQSKit are isolated in bounded processes. On POSIX, timeout or cancellation terminates the owned process group, including BQSKit workers. The default timeout45seconds includes imports/startup; `QLOOM_BASELINE_TIMEOUT` accepts1–300seconds. Native baseline/library errors remain explicit report rows. Python-level baseline verification always runs after compilation and any disclosed phase restoration.

## Provenance

Original training/run source digests in model/benchmark metadata are **historical, partial pipeline fingerprints**, covering the listed training, routing, feature, verifier, cost and generator files at their respective run stages. Later support validation, measured-export checks, adapter fixes, report timing labels and formatting changed source bytes. Do not describe those historical digests as a hash of the final complete experiment source.

`benchmarks/release-source-manifest.json` separately records the current relevant Python source, scripts and project configuration with per-file SHA-256 hashes. `benchmarks/reproduction.json` establishes that a fresh full120-circuit/2880-label retraining exactly matches all48 shipped tree arrays, and that72 fresh held-out learned searches reproduce candidate selection and deterministic metrics. Timing, label-file timing hashes and source metadata naturally change on a rerun. External compiler observations are retained from the actual full experiment; the native reproduction does not claim to remeasure those external times.

The retained demo is an actual earlier run rather than a regenerated illustration. `benchmarks/demo-verification.json` independently rechecks its stored physical outputs and exported classical distributions with the final verification code without altering its historical timing or model digest.

Only project-owned source, reproducible artifacts and original/publicly licensed media are released. Build caches, virtual environments, local render staging, temporary screenshots and task coordination files remain outside the repository. GitHub release assets include the wheel, source distribution, source archive, trained model, original20-second launch film, benchmark evidence and checksums.
