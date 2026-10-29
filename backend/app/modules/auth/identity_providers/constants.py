"""Identity-provider constants."""

#: How long one refresh of an identity-provider token may hold its claim: longer than the provider calls it
#: makes, so a live refresh keeps it, and short enough that a lost worker blocks the next one only briefly.
TOKEN_REFRESH_CLAIM_TTL_SECONDS = 60
