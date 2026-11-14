"""Print the fixed analytic witness and replay the archived example certificate."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from conebound import scalar_witness, verify_certificate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--kappa", default="1")
    parser.add_argument(
        "--certificate",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "certificate_example.json",
    )
    parser.add_argument("--figures", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    args = parser.parse_args()
    result = {"witness": scalar_witness(args.kappa)}
    if not args.certificate.is_file():
        parser.error(f"archived certificate fixture is missing: {args.certificate}")
    fixture = json.loads(args.certificate.read_text())
    result["certificate_replay"] = verify_certificate(fixture["problem"], fixture["certificate"])
    if args.figures:
        figure_script = Path(__file__).resolve().parent / "make_figures.py"
        if not figure_script.is_file():
            parser.error(f"figure script is missing: {figure_script}")
        subprocess.run(
            [sys.executable, str(figure_script), "--output-dir", str(args.output_dir)], check=True
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
