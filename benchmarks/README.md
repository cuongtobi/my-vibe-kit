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

Compare against a previous result without turning timing noise into a hard gate:

```bash
python benchmarks/benchmark_runtime.py \
  --baseline benchmark-baseline.json \
  --comparison-output benchmark-comparison.json \
  --json
```

The result records Python/platform/GitHub-run metadata plus per-size timing deltas when a compatible baseline is available.

Quick smoke:

```bash
python benchmarks/benchmark_runtime.py --sizes 100 --json
```

The benchmark is intended for before/after comparisons on the same machine and Python version. Absolute timings vary with filesystem, Git, CPU, antivirus/indexing software, and runner load.

GitHub Actions:

- normal CI runs the 100-file smoke case;
- the `performance-benchmark` workflow runs on manual dispatch and published releases for 1k/5k/20k on Ubuntu/Python 3.11;
- it restores the most recent same-runner cache as a diagnostic baseline, emits `benchmark-comparison.json`, saves the current result as the next baseline, and uploads SHA-named result/comparison artifacts for 90 days.

Do not turn environment-specific absolute times into hard cross-platform pass/fail thresholds. Use the retained history to investigate regressions against a controlled runner, then reproduce suspicious deltas before treating them as real regressions.
