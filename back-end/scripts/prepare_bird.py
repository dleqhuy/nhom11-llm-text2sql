"""Prepare a reproducible 120/380 split from BIRD Mini-Dev SQLite."""

import argparse
from pathlib import Path

from experiments.dataset import prepare_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path, help="500-row SQLite JSON"
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--source-version", required=True, help="Pinned release or revision"
    )
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    try:
        manifest = prepare_dataset(
            args.source,
            args.output_dir,
            seed=args.seed,
            source_version=args.source_version,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        f"Prepared {manifest['test_count']} test questions and "
        f"{manifest['example_count']} examples in {args.output_dir}"
    )


if __name__ == "__main__":
    main()
