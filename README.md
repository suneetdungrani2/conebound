# CONEBOUND

Research source: https://github.com/suneetdungrani2/conebound.
The accompanying paper is an unreviewed technical manuscript.
Latest corrected manuscript: [v1.0.1](https://github.com/suneetdungrani2/conebound/releases/tag/v1.0.1).
The [original v1.0.0](https://github.com/suneetdungrani2/conebound/releases/tag/v1.0.0) preserves the original paper and unchanged benchmark archive.
The corrected manuscript is published on Zenodo under the existing DOI: [10.5281/zenodo.24217187](https://doi.org/10.5281/zenodo.24217187).

Can one scalar per vector-valued Lorentz-cone contact represent the error
between a log-barrier-smoothed optimizer and its hard-constrained limit?
The paper gives an exact counterexample for every positive smoothing parameter
and an algebraic substitution into Li and Chou's displayed contact equations.
It also describes the restricted isotropic spectral construction and the
established primal–dual gap alternative.

The small Python package independently checks the exact scalar inequality and
archived rational gap certificates. The scripts regenerate all three paper
figures from an analytic example and frozen experimental plot inputs. They do
not rerun robotics experiments or promise a timing-performance improvement.

## Benchmark data

The full benchmark inputs, recorded outcomes, configurations, and verification artifacts are distributed separately from the Git source tree.

**[Download the complete benchmark archive (471 MB)](https://github.com/suneetdungrani2/conebound/releases/download/v1.0.0/conebound-benchmarks-v1.0.0.zip)**

[View the v1.0.0 release and all assets](https://github.com/suneetdungrani2/conebound/releases/tag/v1.0.0) · [Download SHA-256 checksums](https://github.com/suneetdungrani2/conebound/releases/download/v1.0.0/SHA256SUMS.txt)

Verify the download against `data/benchmark_archive.json`, then follow the verified reproduction commands below. The small checked-in files reproduce the analytic example and selected certificate/figures; the full archive supplies the separately recorded benchmark evidence. See the paper for exact limits on what has been rerun.

Install with Python 3.12 (verified on Linux x86_64):

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install -e .
```

Reproduce the counterexample, an actual held-out certificate, and the figures:

```sh
.venv/bin/python scripts/reproduce.py --kappa 1 --figures --output-dir results
.venv/bin/python -m pytest -q
```

The inequality check uses exact rational arithmetic. Its 80-digit witness
coordinates corroborate the proof and are not interval-arithmetic certificates.
The certificate checker uses separate determinant, elimination, cone, and
support-inequality calculations; altered witness/support payloads are rejected.

The paper is [paper/main.pdf](paper/main.pdf); LaTeX and bibliography are in the
same directory, including the full outcome table in `supplement.pdf`. Build after generating figures:

```sh
.venv/bin/python scripts/make_figures.py --output-dir paper/figures
cd paper
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error supplement.tex
cd ..
```

After extracting it beside the checkout, the following commands replay all
embedded validated certificates and reconstruct the small publication inputs:

```sh
.venv/bin/python scripts/verify_archive.py --archive-root ../conebound-benchmarks-v1.0.0
.venv/bin/python scripts/prepare_data.py --study-root ../conebound-benchmarks-v1.0.0/cohorts/corrected --output-dir results/data
```

`data/figure_data.json` records the raw-data hashes and exclusions. The cost/width
scatter takes medians over retained level/repeat rows per base; the paper's
primary timing table uses nested repeat, level, and base medians. The supplement
preserves the legacy numerical implementation for saved-evidence reanalysis.
The minimal package is an extraction, not a replacement for that implementation.

The bank has 240 base problems, with six nested smoothing levels. The original
and protocol-corrected executions use the same bank; they are paired cohorts.
Unknown containment outcomes, failed attempts, and unfavorable comparisons
remain in the evidence. Neither alternative met the complete efficiency criterion.
Physical realization of the substitution remains unproved. The original
researchers' implementation was inspected but not compiled or run, and their
physical robot experiments have not been disproved. No general anisotropic or
coupled spectral repair is established.

Cite: Suneet Dungrani, *A Counterexample to Scalar Smoothing-Error Representations
in Lorentz-Cone Contact Models*, FORGE-CONEBOUND, unreviewed technical manuscript, 2026.
Machine-readable metadata is in [CITATION.cff](CITATION.cff).
No software license is included.
