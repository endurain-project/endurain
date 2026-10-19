import { beforeEach, describe, expect, it } from 'vitest'

import { getApiBaseUrl, getBackendAssetUrl } from '@/services/runtime'

describe('runtime backend configuration', () => {
  beforeEach(() => {
    window.env = undefined
  })

  it('uses ENDURAIN_HOST from env.js for API calls', () => {
    window.env = { ENDURAIN_HOST: 'https://endurain.example.test/' }

    expect(getApiBaseUrl()).toBe('https://endurain.example.test/api/v1')
  })

  it('uses ENDURAIN_HOST from env.js for backend assets', () => {
    window.env = { ENDURAIN_HOST: 'https://endurain.example.test' }

    expect(getBackendAssetUrl('/server_images/login.png')).toBe(
      'https://endurain.example.test/server_images/login.png',
    )
  })

  it('returns an already-absolute asset URL unchanged', () => {
    // Object storage hands back presigned absolute URLs; prefixing the backend
    // host would corrupt them.
    window.env = { ENDURAIN_HOST: 'https://endurain.example.test' }

    expect(getBackendAssetUrl('https://cdn.test/activity_media/5_a.jpg?sig=x')).toBe(
      'https://cdn.test/activity_media/5_a.jpg?sig=x',
    )
  })
})
