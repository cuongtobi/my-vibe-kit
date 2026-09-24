# Runtime benchmark

`benchmark_runtime.py` is a deterministic, standard-library-only scaling benchmark for the local my-vibe-kit runtime.

By default it creates temporary Git repositories with exactly 1,000, 5,000, and 20,000 Python source files arranged as a local import chain. One module contains a token/session refresh symbol so task retrieval has a stable target.

Measured stages:

- full project-context rebuild,
- initial dependency-graph construction,
- unchanged context cache hit,
- unchanged dependency cache hit,
- multilingual relevant-context retrieval,
- one-file incremental context refresh,
- one-file incremental dependency refresh.

Run:

```bash
python benchmarks/benchmark_runtime.py
```

JSON output:

```bash
python benchmarks/benchmark_runtime.py --json
```

Quick smoke:

```bash
python benchmarks/benchmark_runtime.py --sizes 100 --json
```

The benchmark is intended for before/after comparisons on the same machine and Python version. Absolute timings vary with filesystem, Git, CPU, antivirus/indexing software, and runner load.

GitHub Actions:

- normal CI runs the 100-file smoke case;
- the manually dispatched `performance-benchmark` workflow runs 1k/5k/20k on Ubuntu/Python 3.11 and uploads `benchmark-results.json`.

Do not turn environment-specific absolute times into hard cross-platform pass/fail thresholds. Use regressions against a controlled baseline instead.
