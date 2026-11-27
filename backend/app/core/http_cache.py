"""Browser cache lifetimes shared by the routers that serve signed, stable URLs."""

#: Seconds a browser may reuse a signed photo, thumbnail or media response.
SIGNED_URL_CACHE_MAX_AGE = 3600
