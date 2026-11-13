import { describe, expect, it } from 'vitest'

import { mapActivityOwner } from '@/features/activities/services/activityOwner'

import { userUuid } from './fixtures/activity'

describe('mapActivityOwner', () => {
  it('maps the public projection to the owner identity with a servable avatar', () => {
    const owner = mapActivityOwner({
      id: userUuid(7),
      name: 'Jane Runner',
      username: 'jane',
      photo_path: `/api/v1/users/${userUuid(7)}/photo?t=sig`,
    })

    expect(owner).toMatchObject({ name: 'Jane Runner', username: 'jane' })
    expect(owner.avatarUrl).toContain(`/users/${userUuid(7)}/photo?t=sig`)
  })

  it('has no avatar without a photo', () => {
    expect(
      mapActivityOwner({ id: userUuid(7), name: 'Jane', username: 'jane' }).avatarUrl,
    ).toBeNull()
  })
})
