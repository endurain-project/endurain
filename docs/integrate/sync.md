# Keeping a local copy in sync

A client that keeps its own copy of a user's records (a mobile app that works offline) asks `GET /sync` what changed since it last asked, instead of downloading every list again. All paths are under `/api/v1`.

## What it covers

| `type` | Records | Scope |
| ------ | ------- | ----- |
| `activity` | Activities, with `private_notes`, `media` and the thumbnail, as their owner reads them | `activities:read` |
| `health_weight`, `health_steps`, `health_sleep`, `health_water`, `health_poop`, `health_fasting` | Health records; sleep carries its `sleep_stages` | `health:read` |
| `health_targets` | The health targets | `health-targets:read` |
| `gear` | Gear, with its totals | `gears:read` |
| `gear_component` | Gear components | `gears:read` |

Every one of these records carries `updated_at`, when it last changed. It moves on every change, including one the server makes on its own (a map thumbnail, a geocoded place), and `version` moves only when an editable field does.

A gear's `total_distance` and `total_time` are computed from its activities, so a change to an activity does not report the gear again. Read the gear when its activities changed and you show its totals.

Laps, streams, workout sets and workout steps are not synced: they are written once with the activity, so read them when a new activity arrives.

## The loop

```text
GET /sync                        first sync: every record
GET /sync?cursor=<next_cursor>   while has_more is true, right away
...                              has_more is false: store next_cursor
GET /sync?cursor=<stored>        next time: only what changed since
```

A page is `{"changes": [...], "next_cursor": "...", "has_more": false}`. Each change is one record:

```json
{"type": "health_weight", "id": 81, "changed_at": "2026-11-11T07:30:00Z", "record": {"id": 81, "weight_kg": 70.4, "updated_at": "2026-11-11T07:30:00Z", "...": "..."}}
{"type": "activity", "id": 412, "changed_at": "2026-11-11T08:02:11Z", "record": null}
```

- **A change** carries the whole record as `GET` on the record returns it: replace your copy.
- **A deletion** carries `record: null`: delete your copy. A deletion of a record you never had is harmless.
- Changes come oldest first, and the same record can appear twice in one walk when it changed again meanwhile. Apply them in order.
- **Keep `next_cursor` after the last page too.** It is where the next sync starts, and it is renewed on every request, even one that found nothing.
- `num_records` sets the page size (default 100, at most 200). `types` limits the walk to some types; repeat it (`?types=activity&types=gear`). Without `types`, every type your scopes can read is walked, and a type asked for without its scope is `403`.

## Limits

- **Changes appear about two minutes after they happen.** The server holds a change back until every transaction that could still commit an earlier change has ended, so a page never skips one. Do not sync more often than that expecting a fresher answer.
- **A cursor lasts 90 days.** Deletions are remembered for 90 days, so a cursor older than that may have missed one. The server answers `410` with `urn:endurain:error:sync-expired`: discard your copy and sync from the start, with no cursor.
- A cursor is opaque and only this server can read it. A cursor the server did not issue is `400`.
- Deleting the account deletes everything at once and reports nothing: the account can no longer sign in to sync.
