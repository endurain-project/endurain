import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import AppFooter from '@/components/layout/AppFooter.vue'

function mountFooter() {
  return mount(AppFooter, { global: { plugins: [i18n] } })
}

describe('AppFooter', () => {
  it('links to the marketing website, documentation and source code', () => {
    const hrefs = mountFooter()
      .get('nav[aria-label="Project"]')
      .findAll('a')
      .map((link) => link.attributes('href'))

    expect(hrefs).toEqual([
      'https://endurain.com',
      'https://docs.endurain.com',
      'https://github.com/endurain-project/endurain',
    ])
  })

  it('lists the community links as text', () => {
    const labels = mountFooter()
      .get('nav[aria-label="Community"]')
      .findAll('a')
      .map((link) => link.text())

    expect(labels).toEqual(['Discord', 'Mastodon', 'Bluesky', 'LinkedIn'])
  })

  it('opens every footer link in a new tab without leaking the opener', () => {
    for (const link of mountFooter().findAll('a')) {
      expect(link.attributes('target')).toBe('_blank')
      expect(link.attributes('rel')).toBe('noopener noreferrer')
    }
  })
})
