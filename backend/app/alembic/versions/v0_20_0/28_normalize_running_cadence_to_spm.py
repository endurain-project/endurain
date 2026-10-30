"""28: normalize stored running cadence to steps per minute (spm)

Running cadence was stored as the source reported it: FIT, Strava, TCX and GPX
running cadence is a single-leg rate (rpm, around 85) while some treadmill and
footpod sources store full spm (around 160). The importers store spm for running
activities, so existing rows are brought to the same unit.

Only the stored numbers are available here, so the per-activity decision is a
best-effort heuristic, not an exact split: a running activity whose
representative cadence is below 100 is taken as rpm and doubled, one at or above
100 is taken as spm and left untouched. Per-leg running cadence is about 70 to
110 and real spm is almost never below 120, so a slow run above 100 rpm stays in
rpm and a walk logged as a run below 100 spm is doubled.

The representative cadence is a non-zero ``activities.average_cad``, else the
mean of the non-zero cadence stream samples (``stream_type = 3``), else the mean
of the non-zero per-lap cadence with its fraction, else a non-zero ``max_cad``
(a maximum below 100 implies an average below 100); a zero cadence counts as
missing. The decision is taken once per activity, recorded in
``cadence_spm_migration_rows`` together with the original scalars, and applied
to the stream, the laps and the scalars alike. A missing ``average_cad`` takes
the mean it was decided from, if any; a missing ``max_cad`` comes from the
stream, else the laps.

Only plausible activities are touched: cadence is a uint8 in FIT, so an activity
with ``max_cad``, a lap value (with its fraction) or a numeric stream sample
above 255 is left entirely as stored rather than overflowing ``int4``. A
recorded activity has every lap value and numeric stream sample doubled;
non-numeric stream samples are kept as they are. A lap whose fraction is folded
into ``avg_cadence``/``max_cadence`` has its ``*_fractional_cadence`` cleared.

``downgrade()`` restores the recorded activities' original scalars and halves
their lap values and numeric stream samples with integer division: a folded
fraction of 0.75 or more comes back one higher, cleared fractions stay empty,
and a fractional stream sample comes back as an integer.

Revision ID: c91ac2dad0f0
Revises: d54bdd779392
Create Date: 2026-10-19 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c91ac2dad0f0"
down_revision: str | None = "d54bdd779392"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The running activity types (1, 2, 3, 34, 40), the rpm/spm cutoff (100) and the
# plausible cadence ceiling (255) are inlined as a snapshot; a migration must not
# follow later edits to app code. A stream ``cad`` is cast to numeric only when
# it matches ``^[0-9]+([.][0-9]+)?$``, so a non-numeric sample cannot abort it.


def upgrade() -> None:
    """Double running cadence still stored as a single-leg rate."""
    op.execute(
        """
        CREATE TABLE cadence_spm_migration_rows (
            activity_id integer PRIMARY KEY,
            average_cad integer,
            max_cad integer,
            per_leg_avg numeric,
            per_leg_max numeric
        )
        """
    )

    op.execute(
        """
        INSERT INTO cadence_spm_migration_rows (activity_id, average_cad, max_cad, per_leg_avg, per_leg_max)
        WITH stream_samples AS (
            SELECT s.activity_id, v.cad
            FROM activities_streams s
            JOIN activities a ON a.id = s.activity_id AND a.activity_type IN (1, 2, 3, 34, 40)
            CROSS JOIN LATERAL jsonb_array_elements(
                CASE WHEN json_typeof(s.stream_waypoints) = 'array' THEN s.stream_waypoints::jsonb ELSE '[]'::jsonb END
            ) AS t(elem)
            CROSS JOIN LATERAL (
                SELECT CASE WHEN (t.elem ->> 'cad') ~ '^[0-9]+([.][0-9]+)?$' THEN (t.elem ->> 'cad')::numeric END AS cad
            ) AS v
            WHERE s.stream_type = 3
              AND v.cad IS NOT NULL
        ),
        stream_cad AS (
            SELECT activity_id, avg(cad) AS avg_cad, max(cad) AS max_cad
            FROM stream_samples
            WHERE cad > 0
            GROUP BY activity_id
        ),
        lap_cad AS (
            SELECT l.activity_id,
                   avg(COALESCE(
                       NULLIF(l.avg_cadence, 0) + COALESCE(l.avg_fractional_cadence, 0),
                       NULLIF(l.max_cadence, 0) + COALESCE(l.max_fractional_cadence, 0)
                   )) AS avg_cad,
                   max(COALESCE(
                       NULLIF(l.max_cadence, 0) + COALESCE(l.max_fractional_cadence, 0),
                       NULLIF(l.avg_cadence, 0) + COALESCE(l.avg_fractional_cadence, 0)
                   )) AS max_cad
            FROM activity_laps l
            JOIN activities a ON a.id = l.activity_id AND a.activity_type IN (1, 2, 3, 34, 40)
            WHERE COALESCE(NULLIF(l.avg_cadence, 0), NULLIF(l.max_cadence, 0)) IS NOT NULL
            GROUP BY l.activity_id
        ),
        out_of_range AS (
            SELECT activity_id FROM stream_samples WHERE cad > 255
            UNION
            SELECT activity_id
            FROM activity_laps
            WHERE avg_cadence + COALESCE(avg_fractional_cadence, 0) > 255
               OR max_cadence + COALESCE(max_fractional_cadence, 0) > 255
        ),
        decided AS (
            SELECT a.id,
                   a.average_cad,
                   a.max_cad,
                   COALESCE(NULLIF(a.average_cad, 0), sc.avg_cad, lc.avg_cad) AS per_leg_avg,
                   COALESCE(NULLIF(a.max_cad, 0), sc.max_cad, lc.max_cad, a.max_cad) AS per_leg_max
            FROM activities a
            LEFT JOIN stream_cad sc ON sc.activity_id = a.id
            LEFT JOIN lap_cad lc ON lc.activity_id = a.id
            WHERE a.activity_type IN (1, 2, 3, 34, 40)
              AND COALESCE(a.max_cad, 0) <= 255
              AND NOT EXISTS (SELECT 1 FROM out_of_range o WHERE o.activity_id = a.id)
        )
        SELECT id, average_cad, max_cad, per_leg_avg, per_leg_max
        FROM decided
        WHERE COALESCE(per_leg_avg, NULLIF(max_cad, 0)) < 100
        """
    )

    op.execute(
        """
        UPDATE activities_streams s
        SET stream_waypoints = (
            SELECT jsonb_agg(
                CASE
                    WHEN (elem ->> 'cad') IS NULL OR (elem ->> 'cad') !~ '^[0-9]+([.][0-9]+)?$' THEN elem
                    ELSE jsonb_set(elem, '{cad}', to_jsonb(round((elem ->> 'cad')::numeric * 2)::int))
                END
                ORDER BY ord
            )::json
            FROM jsonb_array_elements(s.stream_waypoints::jsonb) WITH ORDINALITY AS t(elem, ord)
        )
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = s.activity_id
          AND s.stream_type = 3
          AND CASE WHEN json_typeof(s.stream_waypoints) = 'array' THEN json_array_length(s.stream_waypoints) > 0 END
        """
    )

    op.execute(
        """
        UPDATE activity_laps l
        SET avg_cadence = round((l.avg_cadence + COALESCE(l.avg_fractional_cadence, 0)) * 2),
            max_cadence = round((l.max_cadence + COALESCE(l.max_fractional_cadence, 0)) * 2),
            avg_fractional_cadence = CASE WHEN l.avg_cadence IS NULL THEN l.avg_fractional_cadence END,
            max_fractional_cadence = CASE WHEN l.max_cadence IS NULL THEN l.max_fractional_cadence END
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = l.activity_id
          AND (l.avg_cadence IS NOT NULL OR l.max_cadence IS NOT NULL)
        """
    )

    op.execute(
        """
        UPDATE activities a
        SET average_cad = round(r.per_leg_avg * 2)::int,
            max_cad = round(r.per_leg_max * 2)::int
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = a.id
        """
    )


def downgrade() -> None:
    """Return the recorded activities' cadence to single-leg rpm.

    The module docstring lists where the inverse is not exact.
    """
    op.execute(
        """
        UPDATE activities_streams s
        SET stream_waypoints = (
            SELECT jsonb_agg(
                CASE
                    WHEN (elem ->> 'cad') IS NULL OR (elem ->> 'cad') !~ '^[0-9]+([.][0-9]+)?$' THEN elem
                    ELSE jsonb_set(elem, '{cad}', to_jsonb(floor((elem ->> 'cad')::numeric / 2)::int))
                END
                ORDER BY ord
            )::json
            FROM jsonb_array_elements(s.stream_waypoints::jsonb) WITH ORDINALITY AS t(elem, ord)
        )
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = s.activity_id
          AND s.stream_type = 3
          AND CASE WHEN json_typeof(s.stream_waypoints) = 'array' THEN json_array_length(s.stream_waypoints) > 0 END
        """
    )

    op.execute(
        """
        UPDATE activity_laps l
        SET avg_cadence = l.avg_cadence / 2,
            max_cadence = l.max_cadence / 2
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = l.activity_id
        """
    )

    op.execute(
        """
        UPDATE activities a
        SET average_cad = r.average_cad,
            max_cad = r.max_cad
        FROM cadence_spm_migration_rows r
        WHERE r.activity_id = a.id
        """
    )

    op.execute("DROP TABLE cadence_spm_migration_rows")
