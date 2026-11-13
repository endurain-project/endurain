import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  getSafeRedirect,
  isNativeRedirect,
  setAllowedRedirectUris,
} from '@/composables/useSafeRedirect'

const APP_CALLBACKS = [
  'endurain://callback',
  'endurain:/oauth2redirect',
  'Endurain:callback',
  'endurain://x',
  'endurain:/x',
]

beforeEach(() => {
  setAllowedRedirectUris(APP_CALLBACKS)
})

afterEach(() => {
  setAllowedRedirectUris([])
})

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
    setAllowedRedirectUris(['endurain://call\nback'])
    expect(getSafeRedirect('endurain://call\nback')).toBe('/')
  })

  it('blocks absolute http(s) URLs', () => {
    expect(getSafeRedirect('https://evil.example/phish')).toBe('/')
  })

  it('blocks paths that smuggle a scheme', () => {
    expect(getSafeRedirect('/redirect://evil.example')).toBe('/')
  })

  it('allows listed native-app custom-scheme deep links', () => {
    expect(getSafeRedirect('endurain://callback')).toBe('endurain://callback')
  })

  it('allows a deep link without an authority, as RFC 3986 ends the scheme at the first colon', () => {
    expect(getSafeRedirect('endurain:/oauth2redirect')).toBe('endurain:/oauth2redirect')
    expect(getSafeRedirect('Endurain:callback')).toBe('Endurain:callback')
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
    expect(getSafeRedirect('blob:https://app.example/uuid')).toBe('/')
    expect(getSafeRedirect('data:text/html,<script>alert(1)</script>')).toBe('/')
  })

  it('falls back to root for empty or non-string values', () => {
    expect(getSafeRedirect(undefined)).toBe('/')
    expect(getSafeRedirect(123)).toBe('/')
  })
})

describe('isNativeRedirect', () => {
  it('recognises a listed app address but not an unlisted http(s) one', () => {
    expect(isNativeRedirect('endurain://x')).toBe(true)
    expect(isNativeRedirect('https://x')).toBe(false)
    expect(isNativeRedirect('/x')).toBe(false)
    expect(isNativeRedirect('https:x')).toBe(false)
  })

  it('reads the scheme up to the first colon only from a well-formed scheme', () => {
    expect(isNativeRedirect('endurain:/x')).toBe(true)
    expect(isNativeRedirect('/endurain:/x')).toBe(false)
    expect(isNativeRedirect('end urain:/x')).toBe(false)
  })

  it('rejects dangerous pseudo-schemes', () => {
    expect(isNativeRedirect('javascript://%0aalert(1)')).toBe(false)
    expect(isNativeRedirect('data://text/html,x')).toBe(false)
    expect(isNativeRedirect('vbscript://x')).toBe(false)
    expect(isNativeRedirect('file://x')).toBe(false)
  })
})

const HTTPS_ADDRESS = 'https://app.example.org/auth/sso/callback'

describe('a claimed-https address', () => {
  it('is native and safe only as an exact listed entry, its scheme in any letter case', () => {
    setAllowedRedirectUris(['HTTPS://app.example.org/auth/sso/callback'])
    expect(isNativeRedirect(HTTPS_ADDRESS)).toBe(true)
    expect(isNativeRedirect('HTTPS://app.example.org/auth/sso/callback')).toBe(true)
    expect(getSafeRedirect(HTTPS_ADDRESS)).toBe(HTTPS_ADDRESS)
  })

  it.each([
    'https://evil.example/auth/sso/callback',
    'HTTPS://evil.example/',
    'https://app.example.org/auth/sso/callback/',
    'https://app.example.org/auth/sso/callback?x=1',
    'https://app.example.org:8443/auth/sso/callback',
    'https:app.example.org/auth/sso/callback',
  ])('refuses the unlisted address %s', (redirect) => {
    setAllowedRedirectUris([HTTPS_ADDRESS])
    expect(isNativeRedirect(redirect)).toBe(false)
    expect(getSafeRedirect(redirect)).toBe('/')
  })

  it('is refused while no address is set', () => {
    setAllowedRedirectUris([])
    expect(isNativeRedirect(HTTPS_ADDRESS)).toBe(false)
    expect(getSafeRedirect(HTTPS_ADDRESS)).toBe('/')
  })

  it.each([
    'https://',
    'https:///callback',
    'https:host/callback',
    'https:/callback',
    'https://user@app.example.org/cb',
    'https://user:pw@app.example.org/cb',
    'https://app.example.org:abc/cb',
    'https://app example.org/cb',
    'https://app.example.org\\cb',
  ])('drops the malformed address %s from the setting', (uri) => {
    setAllowedRedirectUris([uri, 'good://x'])
    expect(isNativeRedirect(uri)).toBe(false)
    expect(getSafeRedirect(uri)).toBe('/')
    expect(isNativeRedirect('good://x')).toBe(true)
  })
})

describe('setAllowedRedirectUris', () => {
  it('allows an exact address', () => {
    setAllowedRedirectUris(['endurain://oauth/callback'])
    expect(isNativeRedirect('endurain://oauth/callback')).toBe(true)
    expect(getSafeRedirect('endurain://oauth/callback')).toBe('endurain://oauth/callback')
  })

  it('matches the scheme case-insensitively and the rest exactly', () => {
    setAllowedRedirectUris(['endurain://oauth/Callback'])
    expect(isNativeRedirect('ENDURAIN://oauth/Callback')).toBe(true)
    expect(isNativeRedirect('endurain://oauth/callback')).toBe(false)
  })

  it('matches an address without an authority, its path case kept', () => {
    setAllowedRedirectUris(['Com.Example.App:/Callback'])
    expect(isNativeRedirect('com.example.app:/Callback')).toBe(true)
    expect(isNativeRedirect('COM.EXAMPLE.APP:/Callback')).toBe(true)
    expect(isNativeRedirect('com.example.app:/callback')).toBe(false)
  })

  it.each([
    'endurain://other',
    'endurain://oauth/callback/extra',
    'endurain://oauth/callback?x=1',
    'endurain://oauth/callback#frag',
  ])('refuses %s, another address under a listed scheme', (redirect) => {
    setAllowedRedirectUris(['endurain://oauth/callback'])
    expect(isNativeRedirect(redirect)).toBe(false)
    expect(getSafeRedirect(redirect)).toBe('/')
  })

  it('allows no custom scheme while no address is set', () => {
    setAllowedRedirectUris([])
    expect(isNativeRedirect('endurain://anything')).toBe(false)
    expect(getSafeRedirect('endurain://anything')).toBe('/')
  })

  it('refuses a scheme that only appears in another listed address', () => {
    setAllowedRedirectUris(['gadgetbridge://auth'])
    expect(isNativeRedirect('gadgetbridge://other')).toBe(false)
    expect(isNativeRedirect('gadgetbridge://auth')).toBe(true)
  })

  it.each([
    'http://x',
    'HTTP://app.example.org/cb',
    'javascript://x',
    'DATA://x',
    'vbscript://x',
    'file://x',
    'blob://x',
    'javascript:alert(1)',
  ])('never allows the unsafe address %s even when configured', (uri) => {
    setAllowedRedirectUris([uri, 'good://x'])
    expect(isNativeRedirect(uri)).toBe(false)
    expect(isNativeRedirect('good://x')).toBe(true)
  })
})
