"""9: normalize running cadence to steps per minute (spm)

Running activities imported before this release stored cadence as the source
reported it. Native Garmin (FIT) running cadence is a single-leg rate (rpm,
~85), while the UI doubled it for display. Other sources (some treadmill/footpod
files) already stored full spm (~160). The importer now normalizes everything to
spm at parse time and the frontend no longer doubles, so existing rows must be
healed to match.

The healing is value-driven, not type-driven: a running activity whose stored
average cadence is below RUNNING_CADENCE_RPM_MAX (120) was recorded as rpm and is
doubled; one at or above 120 already holds spm and is left untouched. Human
running rpm tops out ~110 and running spm starts ~130+, so the split is
unambiguous and already-spm rows (e.g. treadmill) are protected from a spurious
second doubling.

The per-activity decision keys off activities.average_cad and is applied
uniformly to the activity scalar columns, the cadence stream (stream_type = 3),
and the per-lap cadence. Streams and laps are updated first, then the activity
scalars, so every guard still reads the original (pre-doubling) average_cad.

Revision ID: f1a2b3c4d5e6
Revises: a4dd90d4f76e
Create Date: 2026-07-20 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "a4dd90d4f76e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Running/foot activity types (mirrors RUNNING_CADENCE_TYPE_IDS in
# activities/activity/utils.py) and the rpm/spm split threshold (120,
# RUNNING_CADENCE_RPM_MAX) are inlined as literals in the SQL below.


def upgrade() -> None:
    # 1) Cadence stream (stream_type = 3): rebuild the JSON array, doubling each
    #    waypoint's "cad". Guarded on the (still original) activity average_cad.
    op.execute(
        """
        UPDATE activities_streams s
        SET stream_waypoints = (
            SELECT jsonb_agg(
                CASE
                    WHEN elem ? 'cad' AND (elem ->> 'cad') IS NOT NULL
                    THEN jsonb_set(elem, '{cad}', to_jsonb(round((elem ->> 'cad')::numeric * 2)::int))
                    ELSE elem
                END
                ORDER BY ord
            )::json
            FROM jsonb_array_elements(s.stream_waypoints::jsonb) WITH ORDINALITY AS t(elem, ord)
        )
        FROM activities a
        WHERE a.id = s.activity_id
          AND s.stream_type = 3
          AND s.stream_waypoints IS NOT NULL
          AND a.activity_type IN (1, 2, 3, 34, 40)
          AND a.average_cad IS NOT NULL
          AND a.average_cad < 120
        """
    )

    # 2) Per-lap cadence, decided from the parent activity's average_cad.
    op.execute(
        """
        UPDATE activity_laps l
        SET avg_cadence = l.avg_cadence * 2,
            max_cadence = CASE WHEN l.max_cadence IS NOT NULL THEN l.max_cadence * 2 END
        FROM activities a
        WHERE a.id = l.activity_id
          AND a.activity_type IN (1, 2, 3, 34, 40)
          AND a.average_cad IS NOT NULL
          AND a.average_cad < 120
          AND l.avg_cadence IS NOT NULL
        """
    )

    # 3) Activity scalar columns — updated last so the guards above read the
    #    original average_cad.
    op.execute(
        """
        UPDATE activities
        SET average_cad = average_cad * 2,
            max_cad = CASE WHEN max_cad IS NOT NULL THEN max_cad * 2 END
        WHERE activity_type IN (1, 2, 3, 34, 40)
          AND average_cad IS NOT NULL
          AND average_cad < 120
        """
    )


def downgrade() -> None:
    """Not reversible.

    After normalization a doubled rpm row (e.g. 85 → 170) and a natively-spm row
    (e.g. 159) are indistinguishable by value, so the doubling cannot be
    selectively undone without corrupting the already-spm rows. Rolling back the
    schema is safe; the cadence values stay in spm. Re-import the source files if
    the original per-leg values are truly required.
    """
