"""Regenerate the three paper figures from frozen, traceable plot data."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from conebound import restricted_isotropic_spectrum

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/figure_data.json")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    data = json.loads(args.data.read_text())
    args.output_dir.mkdir(parents=True, exist_ok=True)

    def save(fig, name):
        fig.savefig(
            args.output_dir / (name + ".pdf"),
            bbox_inches="tight",
            metadata={"CreationDate": None, "ModDate": None},
        )
        fig.savefig(args.output_dir / (name + ".png"), dpi=180, bbox_inches="tight")
        plt.close(fig)

    analytic = restricted_isotropic_spectrum((2, 1, 0), 1)
    center = np.array(analytic["point"][:2])
    derivative = np.array(analytic["derivative"][:2])
    # At kappa=1, each derivative spectral component supplies one generator.
    generators = np.array([[0.5, 0.5], [0.5, -0.5]]) / np.sqrt([13.0, 5.0])
    polygon = np.array([center - generators @ w for w in ([1, 1], [1, 2], [2, 2], [2, 1], [1, 1])])
    fig, ax = plt.subplots(figsize=(5.5, 3.9))
    ax.fill(polygon[:, 0], polygon[:, 1], alpha=0.18, color="#34699a", label="Two spectral factors")
    endpoints = np.array([center - w * derivative for w in (1, 2)])
    ax.plot(*endpoints.T, color="#b34c40", lw=2.5, label="One scalar factor")
    ax.scatter([0], [0], marker="*", color="black", s=85, label="Exact hard optimum")
    ax.scatter(*center, s=30, color="#34699a", label="Smoothed point")
    ax.set(
        xlabel="Normal coordinate",
        ylabel="Tangential coordinate",
        title="Analytic SOC example, κ = 1",
    )
    ax.axis("equal")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    save(fig, "spectral_geometry")

    misses, attempts = np.array(data["known_rounded_misses"]), np.array(data["attempts"])
    matrix = misses / attempts
    fig, ax = plt.subplots(figsize=(7, 3.6))
    im = ax.imshow(matrix, vmin=0, vmax=1, cmap="Blues", aspect="auto")
    for i in range(len(data["families"])):
        for j in range(len(data["kappas"])):
            ax.text(
                j,
                i,
                f"{misses[i, j]}/{attempts[i, j]}",
                ha="center",
                va="center",
                color="white" if matrix[i, j] > 0.6 else "black",
                fontsize=9,
            )
    ax.set_xticks(range(6), ["10⁻⁶", "10⁻⁴", "10⁻²", "1", "10", "100"])
    ax.set_yticks(range(5), data["families"])
    ax.set(
        xlabel="κ",
        ylabel="Synthetic problem family",
        title="Validated separations from rounded scalar sets",
    )
    fig.colorbar(im, ax=ax, label="Known miss fraction; other cases remain undecided")
    save(fig, "scalar_failure_map")

    fig, ax = plt.subplots(figsize=(6.5, 4))
    for method, color, marker in (
        ("B1", "black", "."),
        ("M1", "#b34c40", "o"),
        ("M2", "#34699a", "s"),
    ):
        points = data["scatter"].get(method, [])
        if points:
            ax.scatter(
                [p["cost_ms"] for p in points],
                [p["width_ratio"] for p in points],
                s=25,
                marker=marker,
                alpha=0.7,
                label=method,
                facecolors="none" if method == "M1" else color,
                edgecolors=color,
            )
    ax.axhline(1.25, color="gray", ls="--", lw=1)
    ax.set(
        xscale="log",
        yscale="log",
        xlabel="Median full method cost (ms)",
        ylabel="Median directional width / B1 width",
        title="Recorded cost–width tradeoff by base problem",
    )
    ax.legend(
        fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncols=3,
    )
    ax.grid(alpha=0.2)
    save(fig, "width_runtime")
    manifest = {
        "figure_data_sha256": sha256(args.data.read_bytes()).hexdigest(),
        "source_sha256": data["source_sha256"],
        "excluded_timing_rows": data["excluded_timing_rows"],
        "scatter_aggregation": data["scatter_aggregation"],
        "limits": data["limits"],
        "outputs_sha256": {
            p.name: sha256(p.read_bytes()).hexdigest()
            for p in sorted(args.output_dir.iterdir())
            if p.suffix in (".png", ".pdf")
        },
    }
    (args.output_dir / "figure_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
