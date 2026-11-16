import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import {
  Image,
  resolveImageSource,
  resolveImageSrcset,
  setImageSourceResolver,
} from '@/components/ui/image'

describe('imageSource resolver', () => {
  afterEach(() => {
    // Restore the default identity behaviour for later tests.
    setImageSourceResolver((src) => src)
  })

  it('returns the URL unchanged by default', () => {
    expect(resolveImageSource('/media/a.png')).toBe('/media/a.png')
  })

  it('applies a registered resolver', () => {
    setImageSourceResolver((src) => `https://cdn.example.com${src}`)
    expect(resolveImageSource('/media/a.png')).toBe('https://cdn.example.com/media/a.png')
  })

  it('resolves each srcset candidate while preserving descriptors', () => {
    setImageSourceResolver((src) => `https://cdn.example.com/${src}`)
    expect(resolveImageSrcset('a.png 1x, a@2x.png 2x')).toBe(
      'https://cdn.example.com/a.png 1x, https://cdn.example.com/a@2x.png 2x',
    )
  })
})

describe('Image', () => {
  afterEach(() => {
    setImageSourceResolver((src) => src)
  })

  it('renders resolved src with accessible alt and lazy defaults', () => {
    const wrapper = mount(Image, { props: { src: '/media/a.png', alt: 'Activity map' } })
    const img = wrapper.find('img')
    expect(img.attributes('src')).toBe('/media/a.png')
    expect(img.attributes('alt')).toBe('Activity map')
    expect(img.attributes('loading')).toBe('lazy')
    expect(img.attributes('decoding')).toBe('async')
  })

  it('routes src and srcset through the active resolver', () => {
    setImageSourceResolver((src) => `https://cdn.example.com${src}`)
    const wrapper = mount(Image, {
      props: { src: '/media/a.png', alt: 'A', srcset: '/media/a.png 1x, /media/a@2x.png 2x' },
    })
    const img = wrapper.find('img')
    expect(img.attributes('src')).toBe('https://cdn.example.com/media/a.png')
    expect(img.attributes('srcset')).toBe(
      'https://cdn.example.com/media/a.png 1x, https://cdn.example.com/media/a@2x.png 2x',
    )
  })

  it('merges a custom class onto the img', () => {
    const wrapper = mount(Image, {
      props: { src: '/media/a.png', alt: 'A', class: 'rounded-full' },
    })
    expect(wrapper.find('img').attributes('class')).toContain('rounded-full')
  })
})
