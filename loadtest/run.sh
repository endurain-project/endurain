#!/usr/bin/env bash
# Run a load-test profile against a disposable distributed deployment.
#
#   ./run.sh smoke       1 api, 1 worker, 2 minutes, small seed (a few minutes in all)
#   ./run.sh standard    2 api, 2 workers, 10 minutes, 50 users x 200 activities
#   ./run.sh soak        2 api, 2 workers, 2 hours (watch memory, connections and queue depth)
#   ./run.sh scale       the same load with 1, 2 and 4 api replicas; records throughput per step
#   ./run.sh faults      2 api, 2 workers, small seed: each fault scenario under a steady load (faults.py), about 20 minutes
#   ./run.sh compare R   print how run R's p95 per group compares with baseline.json (compare.py); exit 1 on a regression
#
# Environment: LOADTEST_KEEP=1 keeps the stack up afterwards; LOADTEST_USERS and LOADTEST_RUNTIME override a
# profile's virtual users and Locust run time (for example 3m, 2h).
#
# Exit status is non-zero when a Locust threshold (thresholds.json) or an invariant (invariants.py) fails.
set -euo pipefail

cd "$(dirname "$0")"
PROFILE="${1:-}"
STAMP="$(date +%Y%m%d-%H%M%S)"
HOST="http://localhost:18080"
# The stack's secrets are made once per checkout and never committed (.gitignore); .env.loadtest holds the rest.
if [ ! -f .env.secrets ]; then
  db_password="$(openssl rand -hex 24)"
  umask 077
  cat > .env.secrets <<SECRETS
SECRET_KEY=$(openssl rand -hex 32)
FERNET_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
DB_PASSWORD=$db_password
POSTGRES_PASSWORD=$db_password
SECRETS
fi
DC=(docker compose -p endurain-load --env-file .env.loadtest --env-file .env.secrets -f compose.yaml)
PSQL=("${DC[@]}" exec -T postgres psql -U endurain -d endurain -X -q)
STATUS=0
SAMPLER_PID=""

case "$PROFILE" in
  smoke)    APIS=(1);       WORKERS=1; USERS=16; SPAWN=4;  RUNTIME=2m;  SEED_USERS=12; SEED_ACTS=30;  SEED_DAYS=120; HEALTH_DAYS=30;  STRAVA_USERS=4 ;;
  standard) APIS=(2);       WORKERS=2; USERS=50; SPAWN=5;  RUNTIME=10m; SEED_USERS=50; SEED_ACTS=200; SEED_DAYS=730; HEALTH_DAYS=90;  STRAVA_USERS=10 ;;
  soak)     APIS=(2);       WORKERS=2; USERS=40; SPAWN=2;  RUNTIME=2h;  SEED_USERS=50; SEED_ACTS=200; SEED_DAYS=730; HEALTH_DAYS=90;  STRAVA_USERS=10 ;;
  scale)    APIS=(1 2 4);   WORKERS=2; USERS=60; SPAWN=6;  RUNTIME=4m;  SEED_USERS=50; SEED_ACTS=200; SEED_DAYS=730; HEALTH_DAYS=90;  STRAVA_USERS=10 ;;
  faults)   APIS=(2);       WORKERS=2; USERS=0;  SPAWN=1;  RUNTIME=0;   SEED_USERS=12; SEED_ACTS=30;  SEED_DAYS=120; HEALTH_DAYS=30;  STRAVA_USERS=6 ;;
  compare)  exec uv run python compare.py "${2:?usage: $0 compare <run>}" ;;
  *) echo "usage: $0 smoke|standard|soak|scale|faults|compare <run>" >&2; exit 2 ;;
esac
USERS="${LOADTEST_USERS:-$USERS}"
RUNTIME="${LOADTEST_RUNTIME:-$RUNTIME}"

cleanup() {
  [ -n "$SAMPLER_PID" ] && kill "$SAMPLER_PID" 2>/dev/null || true
  if [ "${LOADTEST_KEEP:-0}" != "1" ]; then
    echo "== tearing down"
    "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_healthy() {
  for _ in $(seq 1 90); do
    if curl -fsS "$HOST/api/v1/about" >/dev/null 2>&1; then return 0; fi
    sleep 2
  done
  echo "the stack did not become healthy" >&2
  "${DC[@]}" logs --tail 40 api >&2 || true
  return 1
}

# Bring the stack to the shape and seed it.
bring_up_and_seed() {
  local apis="$1"
  # The seed runs in the image as uid 1000 and writes the credentials here; on a CI runner the folder is another user's.
  mkdir -p data && chmod a+rwx data
  "${DC[@]}" up -d --build --wait --scale "api=$apis" --scale "worker=$WORKERS" >/dev/null
  wait_healthy
  sleep 5 # nginx re-resolves the replicas every 2 s

  echo "== seeding ($SEED_USERS users x $SEED_ACTS activities over $SEED_DAYS days, $STRAVA_USERS linked to the stub Strava)"
  "${DC[@]}" run --rm seed --name "$PROFILE" --users "$SEED_USERS" --activities-per-user "$SEED_ACTS" \
    --days "$SEED_DAYS" --health-days "$HEALTH_DAYS" --strava-users "$STRAVA_USERS" 2>&1 \
    | grep -v "tzlocal\|warnings.warn\|^ Container"
}

# One run: bring the stack to the shape, seed, load, check, dump.
run_once() {
  local run="$1" apis="$2" index="$3"
  local dir="results/$run"
  mkdir -p "$dir"
  echo "== $run: $apis api, $WORKERS worker(s), $USERS users, $RUNTIME"
  bring_up_and_seed "$apis"

  "${PSQL[@]}" -c "SELECT pg_stat_statements_reset()" >/dev/null
  # Sample the connections every 5 s for the whole run.
  echo "time,total,active,idle,idle_in_transaction" >"$dir/connections.csv"
  (
    while true; do
      "${PSQL[@]}" -At -F, -c "SELECT now(), count(*), count(*) FILTER (WHERE state = 'active'), \
        count(*) FILTER (WHERE state = 'idle'), count(*) FILTER (WHERE state = 'idle in transaction') \
        FROM pg_stat_activity WHERE datname = 'endurain'" >>"$dir/connections.csv" 2>/dev/null || true
      sleep 5
    done
  ) &
  SAMPLER_PID=$!

  echo "== load"
  local locust_status=0
  LOADTEST_RUN="$run" LOADTEST_RUN_INDEX="$index" LOADTEST_USERS_FILE="data/users.json" \
    uv run locust -f locustfile.py --headless -u "$USERS" -r "$SPAWN" -t "$RUNTIME" --host "$HOST" \
    --csv "$dir/locust" --exit-code-on-error 0 --stop-timeout 60 --only-summary || locust_status=$?
  kill "$SAMPLER_PID" 2>/dev/null || true
  wait "$SAMPLER_PID" 2>/dev/null || true
  SAMPLER_PID=""

  echo "== invariants"
  local inv_status=0
  uv run python invariants.py --run "$run" || inv_status=$?

  echo "== database and container dumps"
  "${PSQL[@]}" -c "SELECT calls, round(total_exec_time::numeric, 1) AS total_ms, round(mean_exec_time::numeric, 2) AS mean_ms, \
    rows, left(regexp_replace(query, '\s+', ' ', 'g'), 150) AS query FROM pg_stat_statements \
    WHERE dbid = (SELECT oid FROM pg_database WHERE datname = 'endurain') ORDER BY total_exec_time DESC LIMIT 20" \
    >"$dir/pg_stat_statements.txt" 2>&1 || true
  "${PSQL[@]}" -c "SELECT state, wait_event_type, wait_event, count(*) FROM pg_stat_activity WHERE datname = 'endurain' \
    GROUP BY 1, 2, 3 ORDER BY 4 DESC" -c "SHOW max_connections" >"$dir/pg_stat_activity.txt" 2>&1 || true
  "${DC[@]}" logs --no-color --no-log-prefix api >"$dir/api.log" 2>&1 || true
  "${DC[@]}" logs --no-color --no-log-prefix worker >"$dir/worker.log" 2>&1 || true
  "${DC[@]}" stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' >"$dir/containers.txt" 2>&1 || true
  local errors
  errors=$(grep -c '"level": "ERROR"' "$dir/api.log" "$dir/worker.log" 2>/dev/null | paste -sd' ' - || true)
  echo "peak connections: $(tail -n +2 "$dir/connections.csv" | cut -d, -f2 | sort -n | tail -1)  error log lines: $errors"
  echo "top statements: $dir/pg_stat_statements.txt"

  if [ "$locust_status" -ne 0 ] || [ "$inv_status" -ne 0 ]; then STATUS=1; fi
  echo "== $run: thresholds $([ "$locust_status" -eq 0 ] && echo ok || echo FAILED), invariants $([ "$inv_status" -eq 0 ] && echo ok || echo VIOLATED)"
}

if [ "$PROFILE" = "faults" ]; then
  RUN="faults-$STAMP"
  mkdir -p "results/$RUN"
  echo "== $RUN: $WORKERS worker(s), ${APIS[0]} api"
  bring_up_and_seed "${APIS[0]}"
  uv run python faults.py --run "$RUN" || STATUS=1
  for service in api worker stub; do
    "${DC[@]}" logs --no-color --no-log-prefix "$service" >"results/$RUN/$service.log" 2>&1 || true
  done
  echo "== $RUN: faults $([ "$STATUS" -eq 0 ] && echo ok || echo FAILED)"
elif [ "$PROFILE" = "scale" ]; then
  GROUP="scale-$STAMP"
  mkdir -p "results/$GROUP"
  index=0
  for apis in "${APIS[@]}"; do
    run_once "$GROUP-api$apis" "$apis" "$index"
    index=$((index + 1))
  done
  python3 - "$GROUP" <<'PY'
import json, sys
group = sys.argv[1]
rows = []
for apis in (1, 2, 4):
    try:
        summary = json.load(open(f"results/{group}-api{apis}/summary.json"))
    except FileNotFoundError:
        continue
    total = summary["total"]
    rows.append({"api_replicas": apis, "rps": total["rps"], "p95_ms": total["p95_ms"], "failures": total["failures"],
                 "throttled": total["throttled"], "requests": total["requests"]})
json.dump(rows, open(f"results/{group}/scale.json", "w"), indent=2)
print("\nscale: throughput per step")
print("api  requests    rps   p95_ms  failures  429")
for r in rows:
    print(f"{r['api_replicas']:>3}  {r['requests']:>8}  {r['rps']:>6.1f}  {r['p95_ms']:>6}  {r['failures']:>8}  {r['throttled']:>3}")
PY
else
  run_once "$PROFILE-$STAMP" "${APIS[0]}" 0
fi

exit "$STATUS"
