/**
 * The entity scope a global search runs against. The three search
 * modes are users, activities and gear; the active scope selects which backend
 * "contains" endpoint the search box queries.
 */
export type SearchScope = 'users' | 'activities' | 'gears'
