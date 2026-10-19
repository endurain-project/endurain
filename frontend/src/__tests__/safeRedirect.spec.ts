import { afterEach, describe, expect, it } from 'vitest'

import {
  getSafeRedirect,
  isCustomSchemeRedirect,
  setAllowedRedirectSchemes,
} from '@/composables/useSafeRedirect'

describe('getSafeRedirect', () => {
  it('allows internal absolute paths', () => {
    expect(getSafeRedirect('/activities')).toBe('/activities')
  })

  it('takes the first value from an array query', () => {
    expect(getSafeRedirect(['/first', '/second'])).toBe('/first')
  })

  it('blocks protocol-relative URLs', () => {
    expect(getSafeRedirect('//evil.example')).toBe('/')
  })

  it.each([
    ['backslash', '/\\evil.example'],
    ['backslash after a slash', '/\\/evil.example'],
    ['tab', '/\t/evil.example'],
    ['line feed', '/\n/evil.example'],
    ['carriage return', '/\r/evil.example'],
  ])('blocks a %s that the browser parses into a protocol-relative URL', (_name, candidate) => {
    // `new URL(candidate, base)` is what assigning to window.location.href does:
    // each of these leaves the origin although none starts with `//`.
    expect(new URL(candidate, 'https://app.example').origin).not.toBe('https://app.example')
    expect(getSafeRedirect(candidate)).toBe('/')
  })

  it.each([
    ['NUL', '/\u0000/x'],
    ['DEL', '/\u007f/x'],
  ])(
    'rejects a %s control character even though the browser keeps it on-origin',
    (_name, candidate) => {
      expect(getSafeRedirect(candidate)).toBe('/')
    },
  )

  it('keeps paths that merely contain odd but harmless characters', () => {
    expect(getSafeRedirect('/activities?type=run&page=2#top')).toBe(
      '/activities?type=run&page=2#top',
    )
    expect(getSafeRedirect('/a%5Cb')).toBe('/a%5Cb')
    expect(getSafeRedirect('/a b')).toBe('/a b')
  })

  it('blocks a control character inside a custom-scheme deep link', () => {
    expect(getSafeRedirect('endurain://call\nback')).toBe('/')
  })

  it('blocks absolute http(s) URLs', () => {
    expect(getSafeRedirect('https://evil.example/phish')).toBe('/')
  })

  it('blocks paths that smuggle a scheme', () => {
    expect(getSafeRedirect('/redirect://evil.example')).toBe('/')
  })

  it('allows native-app custom-scheme deep links', () => {
    expect(getSafeRedirect('endurain://callback')).toBe('endurain://callback')
  })

  it('blocks script-bearing pseudo-scheme redirects', () => {
    // `javascript://` smuggles code past a naive "is it a custom scheme" check;
    // the `//` starts a JS comment and the newline runs the payload when the
    // value is assigned to window.location.href.
    expect(getSafeRedirect('javascript://%0aalert(document.domain)')).toBe('/')
    expect(getSafeRedirect('javascript:alert(1)')).toBe('/')
    expect(getSafeRedirect('data://text/html,<script>alert(1)</script>')).toBe('/')
    expect(getSafeRedirect('vbscript://msgbox(1)')).toBe('/')
    expect(getSafeRedirect('file:///etc/passwd')).toBe('/')
  })

  it('falls back to root for empty or non-string values', () => {
    expect(getSafeRedirect(undefined)).toBe('/')
    expect(getSafeRedirect(123)).toBe('/')
  })
})

describe('isCustomSchemeRedirect', () => {
  it('recognises the allowed app scheme but not http(s)', () => {
    expect(isCustomSchemeRedirect('endurain://x')).toBe(true)
    expect(isCustomSchemeRedirect('https://x')).toBe(false)
    expect(isCustomSchemeRedirect('/x')).toBe(false)
  })

  it('rejects dangerous pseudo-schemes', () => {
    expect(isCustomSchemeRedirect('javascript://%0aalert(1)')).toBe(false)
    expect(isCustomSchemeRedirect('data://text/html,x')).toBe(false)
    expect(isCustomSchemeRedirect('vbscript://x')).toBe(false)
    expect(isCustomSchemeRedirect('file://x')).toBe(false)
  })
})

describe('setAllowedRedirectSchemes', () => {
  afterEach(() => {
    setAllowedRedirectSchemes(['endurain'])
  })

  it('accepts schemes configured on the server', () => {
    const redirect = 'nodomain.freeyourgadget.gadgetbridge://endurain/oauth/callback'
    expect(getSafeRedirect(redirect)).toBe('/')
    setAllowedRedirectSchemes(['endurain', 'nodomain.freeyourgadget.gadgetbridge'])
    expect(getSafeRedirect(redirect)).toBe(redirect)
  })

  it('matches schemes case-insensitively', () => {
    setAllowedRedirectSchemes(['MyApp'])
    expect(isCustomSchemeRedirect('myapp://callback')).toBe(true)
    expect(isCustomSchemeRedirect('MYAPP://callback')).toBe(true)
  })

  it('drops schemes that are no longer configured', () => {
    setAllowedRedirectSchemes(['gadgetbridge'])
    expect(isCustomSchemeRedirect('endurain://callback')).toBe(false)
  })

  it.each(['http', 'https', 'javascript', 'DATA', 'vbscript', 'file'])(
    'never allows the unsafe scheme %s even when configured',
    (scheme) => {
      setAllowedRedirectSchemes([scheme, 'good'])
      expect(isCustomSchemeRedirect(`${scheme}://x`)).toBe(false)
      expect(getSafeRedirect(`${scheme}://x`)).toBe('/')
      expect(isCustomSchemeRedirect('good://x')).toBe(true)
    },
  )

  it('ignores malformed entries', () => {
    setAllowedRedirectSchemes(['', 'not a scheme', '1abc', 'good'])
    expect(isCustomSchemeRedirect('good://x')).toBe(true)
    expect(isCustomSchemeRedirect('1abc://x')).toBe(false)
  })
})
