"""Domain constants for user integrations."""

#: The integration fields a profile export carries and a profile import accepts. The rest of the
#: row is credentials and OAuth state that belongs to the account that linked them, so it never
#: travels in an archive and a crafted archive cannot plant it on the importing account.
PORTABLE_INTEGRATION_FIELDS: tuple[str, ...] = ("strava_sync_gear", "garminconnect_sync_gear")
