import { describe, expect, it } from 'vitest'

import { cn } from '@/lib/utils'

describe('cn', () => {
  it('keeps a custom type-scale utility next to a text colour', () => {
    expect(cn('text-meta font-medium text-foreground')).toBe(
      'text-meta font-medium text-foreground',
    )
    expect(cn('text-body text-foreground')).toBe('text-body text-foreground')
  })

  it('resolves custom type-scale utilities against other font sizes', () => {
    expect(cn('text-sm', 'text-meta')).toBe('text-meta')
    expect(cn('text-body', 'text-hint')).toBe('text-hint')
  })
})
