/**
 * Centralised TanStack Query key factories — the single source of truth for
 * every server-state cache key in the app.
 *
 * Why this exists: query keys are how TanStack Query identifies, caches, and
 * invalidates server data. When keys are hand-written as ad-hoc string arrays
 * (`['notifications']`) scattered across composables and realtime handlers,
 * they silently drift — a typo or a shape change in one place stops matching
 * the other, and invalidations quietly stop working. Routing every key through
 * this factory keeps reads, writes, and invalidations referring to the exact
 * same key.
 *
 * The canonical server-state pattern every feature should follow:
 *   1. service fn   — `apiFetch` + a mapper, in `@/services/<domain>.ts`
 *      (DTO → clean model boundary, e.g. {@link mapUserProfile}).
 *   2. key factory  — a domain entry in {@link queryKeys} below.
 *   3. composable    — `useXxxQuery()` in `@/composables/` calling `useQuery`
 *      with `queryFn` (the service fn) and `queryKey` (the factory).
 *   4. view          — consumes the composable; never calls `fetch`/`apiFetch`
 *      directly and never holds server data in Pinia.
 *
 * For writes, follow the mutation reference in `@/composables/useNotifications`
 * (`useMarkNotificationReadMutation`): optimistic `onMutate` + snapshot,
 * `onError` rollback, and `onSettled` invalidation of the domain's `all()` key.
 *
 * Adding a domain: follow the `notifications` shape — `all()` is the broad
 * prefix used for "invalidate everything in this domain"; `list(filters)` and
 * `detail(id)` narrow from it so partial invalidation (`all()`) cascades to
 * every list and detail query for that domain.
 */
export const queryKeys = {
  /** The authenticated user's profile (seeded by the auth store on login). */
  currentUser: () => ['current-user'] as const,

  /** Unauthenticated settings consumed by the login / sign-up screens. */
  public: {
    serverSettings: () => ['public-server-settings'] as const,
    identityProviders: () => ['public-identity-providers'] as const,
  },

  /**
   * Health domain — the consolidated daily dashboard stats and the user's
   * health targets. Same shape as {@link queryKeys.notifications}: `all()` is
   * the broad prefix so a targets write can cascade to the dashboard.
   */
  health: {
    /** Broad prefix; invalidating this cascades to every health query. */
    all: () => ['health'] as const,
    /** The user's health targets (sleep/steps/weight/… goals). */
    targets: () => ['health', 'targets'] as const,
    /** The consolidated daily dashboard stats (today's metrics + last weight). */
    dashboard: () => ['health', 'dashboard'] as const,
    /** Broad prefix for every paginated weight-history query. */
    weightLists: () => ['health', 'weight'] as const,
    /**
     * @param filters - Serializable list filters (page, size, interval).
     * @returns A weight-history list key scoped to the given filters.
     */
    weight: (filters: Record<string, unknown> = {}) => ['health', 'weight', filters] as const,
    /** Broad prefix for every paginated steps-history query. */
    stepsLists: () => ['health', 'steps'] as const,
    /**
     * @param filters - Serializable list filters (page, size, interval).
     * @returns A steps-history list key scoped to the given filters.
     */
    steps: (filters: Record<string, unknown> = {}) => ['health', 'steps', filters] as const,
    /** Broad prefix for every paginated water-history query. */
    waterLists: () => ['health', 'water'] as const,
    /**
     * @param filters - Serializable list filters (page, size, interval).
     * @returns A water-history list key scoped to the given filters.
     */
    water: (filters: Record<string, unknown> = {}) => ['health', 'water', filters] as const,
    /** Broad prefix for every paginated bowel-movement-history query. */
    poopLists: () => ['health', 'poop'] as const,
    /**
     * @param filters - Serializable list filters (page, size, interval).
     * @returns A bowel-movement-history list key scoped to the given filters.
     */
    poop: (filters: Record<string, unknown> = {}) => ['health', 'poop', filters] as const,
    /** Broad prefix for every paginated resting-heart-rate-history query. */
    rhrLists: () => ['health', 'rhr'] as const,
    /**
     * @param filters - Serializable list filters (page, size, interval).
     * @returns A resting-heart-rate-history list key scoped to the given filters.
     */
    rhr: (filters: Record<string, unknown> = {}) => ['health', 'rhr', filters] as const,
    /** Broad prefix for every fasting query (history, active session, stats). */
    fastingLists: () => ['health', 'fasting'] as const,
    /**
     * @param filters - Serializable list filters (page, size, interval).
     * @returns A fasting-history list key scoped to the given filters.
     */
    fasting: (filters: Record<string, unknown> = {}) => ['health', 'fasting', filters] as const,
    /** The user's active (in-progress) fasting session, or `null`. */
    fastingActive: () => ['health', 'fasting', 'active'] as const,
    /** Aggregate fasting statistics (streaks, totals, completion rate). */
    fastingStats: () => ['health', 'fasting', 'stats'] as const,
    /** Broad prefix for every paginated sleep-history query. */
    sleepLists: () => ['health', 'sleep'] as const,
    /**
     * @param filters - Serializable list filters (page, size, interval).
     * @returns A sleep-history list key scoped to the given filters.
     */
    sleep: (filters: Record<string, unknown> = {}) => ['health', 'sleep', filters] as const,
  },

  /** Reference domain factory — copy this shape for activities, gears, etc. */
  notifications: {
    /** Broad prefix; invalidating this cascades to every notifications query. */
    all: () => ['notifications'] as const,
    lists: () => ['notifications', 'list'] as const,
    /**
     * @param filters - Serializable list filters (paging, type, etc.).
     * @returns A list query key scoped to the given filters.
     */
    list: (filters: Record<string, unknown> = {}) => ['notifications', 'list', filters] as const,
    /**
     * Unread badge count. Deliberately outside the `list` prefix so the
     * optimistic mark-read updater (which rewrites `lists()`) leaves it alone;
     * the mutation's `onSettled` invalidates `all()`, refetching this for the
     * server-authoritative count.
     */
    unreadCount: () => ['notifications', 'unread-count'] as const,
    details: () => ['notifications', 'detail'] as const,
    /**
     * @param id - Notification identifier.
     * @returns A detail query key for a single notification.
     */
    detail: (id: number) => ['notifications', 'detail', id] as const,
  },

  /**
   * Activities domain. New activities are created via the file-upload reference
   * (`@/features/upload`); its mutation invalidates `all()` on settle so every
   * activities list refetches. Same shape as {@link queryKeys.notifications} —
   * extend with `details`/`detail` when the activities feature lands.
   */
  activities: {
    /** Broad prefix; invalidating this cascades to every activities query. */
    all: () => ['activities'] as const,
    lists: () => ['activities', 'list'] as const,
    /**
     * @param filters - Serializable list filters (paging, type, etc.).
     * @returns A list query key scoped to the given filters.
     */
    list: (filters: Record<string, unknown> = {}) => ['activities', 'list', filters] as const,
    details: () => ['activities', 'detail'] as const,
    /**
     * @param name - The activity-name search term.
     * @returns A query key for a name "contains" search.
     */
    search: (name: string) => ['activities', 'search', name] as const,
    /**
     * @param id - Activity identifier.
     * @returns A detail query key for a single activity.
     */
    detail: (id: number) => ['activities', 'detail', id] as const,
    /**
     * @param id - Activity identifier.
     * @returns A query key for an activity's metric streams.
     */
    streams: (id: number) => ['activities', 'detail', id, 'streams'] as const,
    /**
     * @param id - Activity identifier.
     * @returns A query key for an activity's laps.
     */
    laps: (id: number) => ['activities', 'detail', id, 'laps'] as const,
    /** Planned workout steps for one activity. */
    workoutSteps: (id: number) => ['activities', 'detail', id, 'workout-steps'] as const,
    /** Performed workout sets for one activity. */
    sets: (id: number) => ['activities', 'detail', id, 'sets'] as const,
    /** The exercise-name catalogue (shared across activities). */
    exerciseTitles: () => ['activities', 'exercise-titles'] as const,
    /** Media (photos) attached to one activity. */
    media: (id: number) => ['activities', 'detail', id, 'media'] as const,
    /** The activity's owner user (public or authenticated), keyed by user id. */
    owner: (userId: number) => ['activities', 'owner', userId] as const,
    /** The distinct activity-type codes the user owns (type-filter options). */
    types: () => ['activities', 'types'] as const,
    /** The user's activity-type code→name map (summary type filter). */
    typeNames: () => ['activities', 'type-names'] as const,
    /**
     * An aggregated activity summary for a view type + period + optional type
     * filter (the `/summary` view). Under the `activities` prefix so an `all()`
     * invalidation after an upload/delete refetches it.
     *
     * @param params - Serializable summary params (view type, date/year, type).
     * @returns A summary query key scoped to those params.
     */
    summary: (params: Record<string, unknown> = {}) => ['activities', 'summary', params] as const,
    /**
     * The home dashboard's infinite feed of a user's own activities. Under the
     * `list` prefix so an `all()` invalidation (e.g. after upload/delete)
     * refetches it.
     *
     * @param userId - The feed owner's user id.
     * @param pageSize - Records per page (the only paging filter; the infinite
     *   query keys on size, not page number, so all pages share one entry).
     * @returns A list query key for the user's home feed.
     */
    userFeed: (userId: number, pageSize: number) =>
      ['activities', 'list', { scope: 'user-feed', userId, pageSize }] as const,
    /**
     * The home dashboard's feed of activities from people the user follows.
     *
     * @param userId - The viewer's user id.
     * @param pageSize - Records per page.
     * @returns A list query key for the followed-users feed.
     */
    followersFeed: (userId: number, pageSize: number) =>
      ['activities', 'list', { scope: 'followers-feed', userId, pageSize }] as const,
    /**
     * A user's per-sport aggregated stats for a timeframe (home dashboard).
     *
     * @param userId - The user whose stats to key.
     * @param timeframe - `week` or `month`.
     * @returns A stats query key.
     */
    stats: (userId: number, timeframe: 'week' | 'month') =>
      ['activities', 'stats', userId, timeframe] as const,
    /**
     * A user's activity count for the current month (public-profile header).
     *
     * @param userId - The user whose monthly count to key.
     * @returns A query key for the user's this-month activity count.
     */
    monthCount: (userId: number) => ['activities', 'month-count', userId] as const,
    /**
     * A user's activities for a single ISO week (public-profile week browser).
     * Under the `list` prefix so an `all()` invalidation refetches it.
     *
     * @param userId - The profile owner's user id.
     * @param week - Week offset (0 = this week).
     * @returns A list query key for that week's activities.
     */
    weekActivities: (userId: number, week: number) =>
      ['activities', 'list', { scope: 'user-week', userId, week }] as const,
  },

  /**
   * Gears domain. Same shape as {@link queryKeys.notifications}: `all()` is the
   * broad prefix for "invalidate every gears query", which the create/update/
   * delete mutations invalidate on settle so lists, the nickname search, and
   * detail views all refetch the server-authoritative state.
   */
  gears: {
    /** Broad prefix; invalidating this cascades to every gears query. */
    all: () => ['gears'] as const,
    lists: () => ['gears', 'list'] as const,
    /**
     * @param filters - Serializable list filters (page size, show-inactive).
     * @returns A list query key scoped to the given filters.
     */
    list: (filters: Record<string, unknown> = {}) => ['gears', 'list', filters] as const,
    /**
     * @param nickname - The nickname search term.
     * @returns A query key for a nickname "contains" search.
     */
    search: (nickname: string) => ['gears', 'search', nickname] as const,
    details: () => ['gears', 'detail'] as const,
    /**
     * @param id - Gear identifier.
     * @returns A detail query key for a single gear.
     */
    detail: (id: number) => ['gears', 'detail', id] as const,
    /** Broad prefix for every gear-components query (all gears). */
    componentsLists: () => ['gears', 'components'] as const,
    /**
     * @param gearId - Parent gear identifier.
     * @returns A query key for one gear's component list.
     */
    components: (gearId: number) => ['gears', 'components', gearId] as const,
    /** The static component-type catalogues (cached for the session). */
    componentTypes: () => ['gears', 'component-types'] as const,
    /** Gears grouped by type for the default-gear selectors (under the gears prefix so gear writes refresh it). */
    typeOptions: () => ['gears', 'type-options'] as const,
    /** Gears of a single type, for the per-activity gear picker. */
    byType: (gearType: number) => ['gears', 'by-type', gearType] as const,
    /** Broad prefix for every gear-activities query (all gears). */
    activitiesLists: () => ['gears', 'activities'] as const,
    /**
     * @param gearId - Parent gear identifier.
     * @param filters - Serializable list filters (paging).
     * @returns A query key for one gear's paginated activities list.
     */
    activities: (gearId: number, filters: Record<string, unknown> = {}) =>
      ['gears', 'activities', gearId, filters] as const,
  },

  /**
   * Users administration domain (admin settings zone). Same shape as
   * {@link queryKeys.notifications}: `all()` is the broad prefix the create/
   * update/delete mutations invalidate on settle so every list, the username
   * search, and detail views refetch the server-authoritative state.
   */
  users: {
    /** Broad prefix; invalidating this cascades to every users query. */
    all: () => ['users'] as const,
    lists: () => ['users', 'list'] as const,
    /**
     * @param filters - Serializable list filters (page, size, show-inactive).
     * @returns A list query key scoped to the given filters.
     */
    list: (filters: Record<string, unknown> = {}) => ['users', 'list', filters] as const,
    /**
     * @param username - The username search term.
     * @returns A query key for a username "contains" search.
     */
    search: (username: string) => ['users', 'search', username] as const,
    /** Detail-view prefix; invalidating this refetches every user detail. */
    details: () => ['users', 'detail'] as const,
    /**
     * @param id - The user id.
     * @returns A query key for a single user's detail.
     */
    detail: (id: number) => ['users', 'detail', id] as const,
    /**
     * A user's public-facing profile (name/username/city/avatar), as shown on
     * the `/user/:id` page and in follower/following lists. Distinct from
     * {@link detail} (the admin `ManagedUser` shape) so the two never collide in
     * the cache.
     *
     * @param id - The user id.
     * @returns A query key for a single user's public profile.
     */
    publicProfile: (id: number) => ['users', 'public-profile', id] as const,
    /**
     * @param userId - The session owner's id.
     * @returns A query key for a user's active-sessions list.
     */
    sessions: (userId: number) => ['users', 'sessions', userId] as const,
    /**
     * @param userId - The user whose identity-provider links to key.
     * @returns A query key for a user's linked identity providers.
     */
    identityProviders: (userId: number) => ['users', 'identity-providers', userId] as const,
  },

  /**
   * Social graph domain (follow relationships). Same shape as
   * {@link queryKeys.notifications}: `all()` is the broad prefix the follow,
   * unfollow, accept, and remove mutations invalidate on settle so every list,
   * count, and relationship-state query refetches the server-authoritative
   * state.
   */
  followers: {
    /** Broad prefix; invalidating this cascades to every follow-graph query. */
    all: () => ['followers'] as const,
    /**
     * The people who follow a user (the user's followers list).
     *
     * @param userId - The profile owner whose followers to key.
     * @returns A query key for a user's followers list.
     */
    followersList: (userId: number) => ['followers', 'followers', userId] as const,
    /**
     * The people a user follows (the user's following list).
     *
     * @param userId - The profile owner whose following list to key.
     * @returns A query key for a user's following list.
     */
    followingList: (userId: number) => ['followers', 'following', userId] as const,
    /**
     * A user's accepted-followers count (public-profile header).
     *
     * @param userId - The profile owner whose follower count to key.
     * @returns A query key for a user's accepted-followers count.
     */
    followersCount: (userId: number) => ['followers', 'followers-count', userId] as const,
    /**
     * A user's accepted-following count (public-profile header).
     *
     * @param userId - The profile owner whose following count to key.
     * @returns A query key for a user's accepted-following count.
     */
    followingCount: (userId: number) => ['followers', 'following-count', userId] as const,
    /**
     * The viewer → target follow relationship state, backing the follow button.
     *
     * @param viewerId - The authenticated viewer's id.
     * @param targetId - The profile owner's id.
     * @returns A query key for the viewer's relationship to the target.
     */
    state: (viewerId: number, targetId: number) =>
      ['followers', 'state', viewerId, targetId] as const,
  },

  /**
   * Server settings domain (admin). The singleton settings object and the
   * static tile-map presets each get a key; the edit mutation invalidates
   * `all()` on settle so the form refetches the server-authoritative state.
   */
  serverSettings: {
    /** Broad prefix; invalidating this cascades to every server-settings query. */
    all: () => ['server-settings'] as const,
    /** The singleton server-settings object. */
    detail: () => ['server-settings', 'detail'] as const,
    /** The static catalogue of selectable tile-server presets. */
    tileTemplates: () => ['server-settings', 'tile-templates'] as const,
  },

  /**
   * Event-log observability domain (admin). The aggregated dashboard summary is
   * keyed by its look-back window so changing the window fetches a fresh slice.
   */
  eventLog: {
    /** Broad prefix; invalidating this cascades to every event-log query. */
    all: () => ['event-log'] as const,
    /**
     * @param hours - The look-back window in hours.
     * @returns A summary query key scoped to that window.
     */
    summary: (hours: number) => ['event-log', 'summary', hours] as const,
  },

  /**
   * Durable-jobs domain (admin). The processing summary is keyed by its
   * look-back window; replaying a dead-letter job invalidates the whole domain.
   */
  jobs: {
    /** Broad prefix; invalidating this cascades to every jobs query. */
    all: () => ['jobs'] as const,
    /**
     * @param hours - The look-back window in hours.
     * @returns A summary query key scoped to that window.
     */
    summary: (hours: number) => ['jobs', 'summary', hours] as const,
  },

  /**
   * Identity providers domain (admin SSO config). `all()` is the broad prefix
   * the create/update/delete mutations invalidate on settle so the list (and
   * any derived view) refetches the server-authoritative state.
   */
  identityProviders: {
    /** Broad prefix; invalidating this cascades to every IdP query. */
    all: () => ['identity-providers'] as const,
    /** The admin list of all configured providers. */
    list: () => ['identity-providers', 'list'] as const,
    /** The static catalogue of provider presets. */
    templates: () => ['identity-providers', 'templates'] as const,
  },

  /**
   * The authenticated user's own settings profile (identity + privacy). Kept
   * separate from {@link queryKeys.currentUser} (the narrow shell model): the
   * profile zone needs the full field set, and its edits invalidate both keys.
   */
  profile: {
    /** Broad prefix; invalidating this cascades to every profile query. */
    all: () => ['profile'] as const,
    /** The full self-profile (identity + privacy). */
    detail: () => ['profile', 'detail'] as const,
    /** The user's per-activity default-gear assignments. */
    defaultGear: () => ['profile', 'default-gear'] as const,
  },

  /**
   * The authenticated user's fitness goals (account settings zone). `all()` is
   * the broad prefix the create/update/delete mutations invalidate on settle so
   * the list refetches the server-authoritative state.
   */
  goals: {
    /** Broad prefix; invalidating this cascades to every goals query. */
    all: () => ['goals'] as const,
    /**
     * @param filters - Serializable list filters (interval, activity type, goal type).
     * @returns A list query key scoped to the given filters.
     */
    list: (filters: Record<string, unknown> = {}) => ['goals', 'list', filters] as const,
    /** Per-goal progress for the current interval (home dashboard panel). */
    results: () => ['goals', 'results'] as const,
  },

  /**
   * Core application metadata fetched from the backend and external sources.
   */
  core: {
    /** The running backend's version (`/about`). */
    aboutVersion: () => ['core', 'about-version'] as const,
    /** The latest published stable release tag from the upstream repository. */
    latestRelease: () => ['core', 'latest-release'] as const,
    /** The latest published pre-release tag from the upstream repository. */
    latestPreRelease: () => ['core', 'latest-pre-release'] as const,
  },

  /**
   * The authenticated user's account security state (MFA, backup codes, active
   * sessions). `all()` is the broad prefix the security mutations invalidate so
   * the affected cards refetch the server-authoritative state.
   */
  security: {
    /** Broad prefix; invalidating this cascades to every security query. */
    all: () => ['security'] as const,
    /** Whether MFA (TOTP) is enabled. */
    mfaStatus: () => ['security', 'mfa-status'] as const,
    /** The remaining-backup-codes summary. */
    backupCodeStatus: () => ['security', 'backup-code-status'] as const,
    /** The user's active sessions. */
    sessions: () => ['security', 'sessions'] as const,
    /** The user's linked identity providers. */
    linkedProviders: () => ['security', 'linked-providers'] as const,
    /** The user's API keys. */
    apiKeys: () => ['security', 'api-keys'] as const,
  },
} as const
