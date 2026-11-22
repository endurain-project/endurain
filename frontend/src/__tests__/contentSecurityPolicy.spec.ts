import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/** Every `.vue` file under `dir`, recursively. */
function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return vueFiles(path)
    return entry.name.endsWith('.vue') ? [path] : []
  })
}

describe('content security policy', () => {
  it('ships a meta policy that allows no inline script or style', () => {
    const config = readFileSync(join(process.cwd(), 'vite.config.ts'), 'utf8')
    const policy = config.slice(config.indexOf('CONTENT_SECURITY_POLICY = ['))

    expect(policy).toContain(`"script-src 'self'"`)
    expect(policy).toContain(`"style-src 'self'"`)
    expect(policy).not.toContain('unsafe-inline')
  })

  // style-src refuses a `style` attribute in parsed markup but not a CSSOM write, which is what `:style` does.
  it('has no static style attribute in any template', () => {
    const offenders = vueFiles(join(process.cwd(), 'src')).filter((file) =>
      /(?<![:\w-])style\s*=\s*["']/.test(readFileSync(file, 'utf8').split('<style')[0] ?? ''),
    )

    expect(offenders).toEqual([])
  })
})
