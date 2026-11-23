"""Sum up what a run's samplers recorded (run.sh): CPU and memory per container, queues, locks, connections, Redis.

    uv run python resources.py results/<run> <cpus>    (cpus: the Docker VM's, docker info's NCPU)

Memory growth compares each container's median over the second tenth of the load with the median over its last tenth,
so the warm-up and a single spike decide nothing: steady growth across a soak is a leak to look into. The CPU line sums
every container, against what the Docker VM has, so contention between the containers shows. It reports and never fails
the run: it has no baseline to judge against.
"""

import csv
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

_UNITS = {"B": 1 / 2**20, "KiB": 1 / 2**10, "kB": 1 / 2**10, "MiB": 1, "MB": 1, "GiB": 2**10, "GB": 2**10}


def mib(usage: str) -> float:
    """The used part of a ``docker stats`` memory column (``210.6MiB / 5.764GiB``), in MiB."""
    match = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)", usage)
    if not match:
        raise ValueError(f"unreadable memory usage: {usage!r}")
    return float(match.group(1)) * _UNITS[match.group(2)]


def tenth(values: list[float], index: int) -> float:
    """The median of the ``index``-th tenth of ``values`` (0-based)."""
    size = max(1, len(values) // 10)
    return statistics.median(values[index * size : (index + 1) * size] or values[-size:])


def rows(path: Path) -> list[dict[str, str]]:
    """The rows of a sampler CSV, or none when the sampler wrote nothing."""
    return list(csv.DictReader(path.open())) if path.exists() else []


def containers(path: Path, cpus: int) -> None:
    """Print CPU and memory per container, and the summed CPU against the ``cpus`` of the Docker VM."""
    cpu: dict[str, list[float]] = defaultdict(list)
    memory: dict[str, list[float]] = defaultdict(list)
    total_cpu: dict[str, float] = defaultdict(float)
    for row in rows(path):
        name = row["container"].removeprefix("endurain-load-")
        percent = float(row["cpu_percent"].rstrip("%"))
        cpu[name].append(percent)
        memory[name].append(mib(row["memory"]))
        total_cpu[row["time"]] += percent
    if not cpu:
        print("containers: no samples")
        return
    print(f"{'container':<22} {'cpu mean':>9} {'cpu p95':>8} {'mem start':>10} {'mem end':>8} {'mem peak':>9}  growth")
    for name in sorted(cpu, key=lambda n: -statistics.mean(cpu[n])):
        start, end = tenth(memory[name], 1), tenth(memory[name], 9)
        growth = (end - start) / start * 100 if start else 0.0
        print(
            f"{name:<22} {statistics.mean(cpu[name]):>8.0f}% {percentile(cpu[name], 95):>7.0f}% "
            f"{start:>8.0f}Mi {end:>6.0f}Mi {max(memory[name]):>7.0f}Mi  {growth:+.0f}%"
        )
    totals = list(total_cpu.values())
    print(
        f"all containers: cpu mean {statistics.mean(totals):.0f}%, p95 {percentile(totals, 95):.0f}% "
        f"of {cpus * 100}% ({cpus} CPUs)"
    )


def percentile(values: list[float], pct: int) -> float:
    """The ``pct``-th percentile of ``values`` (nearest rank)."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))]


def queues(path: Path) -> None:
    """Print each queue's peak of due, deferred and claimed jobs."""
    peak: dict[str, dict[str, int]] = defaultdict(lambda: {"due": 0, "deferred": 0, "claimed": 0})
    for row in rows(path):
        for column in ("due", "deferred", "claimed"):
            peak[row["queue"]][column] = max(peak[row["queue"]][column], int(row[column]))
    if not peak:
        print("queues: never a job open at a sample")
        return
    print(
        "queues (peak): "
        + "; ".join(
            f"{q} due {p['due']}, deferred {p['deferred']}, claimed {p['claimed']}" for q, p in sorted(peak.items())
        )
    )


def database(path: Path) -> None:
    """Print the peak connections and the sessions waiting on a lock."""
    samples = rows(path)
    if not samples:
        print("connections: no samples")
        return
    waits = [int(r["lock_waits"]) for r in samples]
    print(
        f"connections: peak {max(int(r['total']) for r in samples)}, idle in transaction peak "
        f"{max(int(r['idle_in_transaction']) for r in samples)}; sessions waiting on a lock: peak {max(waits)}, "
        f"in {sum(1 for w in waits if w) * 100 // len(waits)}% of samples"
    )


def redis(path: Path) -> None:
    """Print Redis's keys and memory at the start, the end and the peak."""
    samples = rows(path)
    if not samples:
        print("redis: no samples")
        return
    keys = [int(r["keys"]) for r in samples]
    memory = [int(r["used_memory"]) / 2**20 for r in samples]
    print(
        f"redis: keys {keys[0]} -> {keys[-1]} (peak {max(keys)}), memory {memory[0]:.1f} -> {memory[-1]:.1f} MiB "
        f"(peak {max(memory):.1f})"
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: resources.py results/<run> <cpus>", file=sys.stderr)
        return 2
    run = Path(sys.argv[1])
    containers(run / "containers.csv", int(sys.argv[2]))
    queues(run / "queues.csv")
    database(run / "connections.csv")
    redis(run / "redis.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
