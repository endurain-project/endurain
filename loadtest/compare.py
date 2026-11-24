"""Compare a run's p95 per group with the committed baseline.

    uv run python compare.py <run>                    print the comparison; exit 1 when a group regressed
    uv run python compare.py <run> --write-baseline   write baseline.json from the run

A group regresses when its p95 is more than ``--factor`` times the baseline's and also more than ``--floor-ms`` above
it: the factor catches a real slowdown, and the floor keeps a 6 ms -> 11 ms wobble on a shared CI runner from failing a
run. The groups that wait on polling (``*_e2e``, ``*_hint``) use ``--poll-floor-ms``, since their time is made of
1-2 second poll intervals. A baseline is only compared with a run of the same profile; regenerate it on the machine
that runs the comparison (a CI runner is slower than a laptop, and the first scheduled run shows by how much).
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = Path(os.environ.get("LOADTEST_RESULTS", HERE / "results"))
BASELINE = HERE / "baseline.json"
#: A group's p95 may grow to this many times the baseline's.
FACTOR = 1.5


def profile_of(run: str) -> str:
    """The profile a run was made with: ``standard-20261121-105410`` is ``standard``."""
    return run.split("-", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run", help="a folder name under results/")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    parser.add_argument("--factor", type=float, default=FACTOR)
    parser.add_argument("--floor-ms", type=float, default=50.0)
    parser.add_argument("--poll-floor-ms", type=float, default=2000.0)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()

    summary = json.loads((RESULTS / args.run / "summary.json").read_text())
    groups = {
        name: {"p95_ms": row["p95_ms"], "requests": row["requests"], "rps": row["rps"]}
        for name, row in summary["groups"].items()
        if row["status"] != "skipped"
    }
    if args.write_baseline:
        baseline = {
            "profile": profile_of(summary["run"]),
            "generated": date.today().isoformat(),
            "run": summary["run"],
            "total": {key: summary["total"][key] for key in ("requests", "rps", "p95_ms", "failures")},
            "groups": groups,
        }
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n")
        print(f"wrote {args.baseline} from {summary['run']}")
        return 0

    baseline = json.loads(args.baseline.read_text())
    if baseline["profile"] != profile_of(summary["run"]):
        print(
            f"baseline is for the {baseline['profile']} profile, this run is {profile_of(summary['run'])}: not compared"
        )
        return 0
    print(
        f"p95 per group against {args.baseline.name} ({baseline['run']}, {baseline['generated']}); "
        f"regression = more than {args.factor}x and more than the floor above"
    )
    print(f"{'group':<16}{'baseline':>10}{'now':>8}{'ratio':>7}{'floor':>7}  result")
    regressions = []
    for name, now in sorted(groups.items()):
        was = baseline["groups"].get(name)
        if was is None:
            print(f"{name:<16}{'-':>10}{now['p95_ms']:>8}{'-':>7}{'-':>7}  new group")
            continue
        floor = args.poll_floor_ms if name.endswith(("_e2e", "_hint")) else args.floor_ms
        ratio = now["p95_ms"] / was["p95_ms"] if was["p95_ms"] else 1.0
        bad = ratio > args.factor and now["p95_ms"] - was["p95_ms"] > floor
        if bad:
            regressions.append(f"{name}: p95 {was['p95_ms']} -> {now['p95_ms']} ms ({ratio:.2f}x)")
        print(
            f"{name:<16}{was['p95_ms']:>10}{now['p95_ms']:>8}{ratio:>7.2f}{floor:>7.0f}  {'REGRESSED' if bad else 'ok'}"
        )
    for name in sorted(set(baseline["groups"]) - set(groups)):
        print(f"{name:<16}{baseline['groups'][name]['p95_ms']:>10}{'-':>8}{'-':>7}{'-':>7}  not in this run")
    now_total, was_total = summary["total"], baseline["total"]
    print(
        f"total: {now_total['rps']} rps (baseline {was_total['rps']}), p95 {now_total['p95_ms']} ms (baseline {was_total['p95_ms']})"
    )
    for line in regressions:
        print(f"REGRESSION: {line}")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
