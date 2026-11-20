import DOMPurify from 'dompurify'
import { marked } from 'marked'

/**
 * Renders user/federated markdown to sanitized HTML.
 *
 * This is the single place markdown becomes HTML. The output is sanitized with
 * DOMPurify against a strict tag/attribute allow-list, so the result is safe to
 * inject via `v-html` (done only inside `SafeHtml.vue`).
 */

/** HTML tags permitted in rendered markdown output. */
const ALLOWED_TAGS = [
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'p',
  'br',
  'hr',
  'ul',
  'ol',
  'li',
  'blockquote',
  'code',
  'pre',
  'strong',
  'em',
  'del',
  'a',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
]

/** HTML attributes permitted in rendered markdown output. */
const ALLOWED_ATTR = ['href', 'title', 'target', 'rel']

let hookRegistered = false

/**
 * Forces every rendered link to open safely in a new tab. Registered once,
 * lazily, so importing this module has no side effects until it is used.
 */
function ensureLinkHook(): void {
  if (hookRegistered) {
    return
  }
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.tagName === 'A') {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
  })
  hookRegistered = true
}

marked.setOptions({ breaks: true, gfm: true })

/**
 * Converts a markdown string to sanitized HTML.
 *
 * @param markdown - The raw markdown to render (nullish is treated as empty).
 * @returns Sanitized HTML safe for rendering, or an empty string.
 */
export function renderMarkdown(markdown: string | null | undefined): string {
  if (!markdown || typeof markdown !== 'string') {
    return ''
  }
  ensureLinkHook()
  // `async: false` (the default) makes `parse` return a string synchronously.
  const rawHtml = marked.parse(markdown, { async: false })
  return DOMPurify.sanitize(rawHtml, { ALLOWED_TAGS, ALLOWED_ATTR })
}
