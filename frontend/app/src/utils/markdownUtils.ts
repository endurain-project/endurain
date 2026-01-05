import { marked } from 'marked'
import DOMPurify from 'dompurify'

/**
 * Allowed HTML tags for markdown rendering.
 */
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
  'td'
]

/**
 * Allowed HTML attributes for markdown rendering.
 */
const ALLOWED_ATTR = ['href', 'title', 'target', 'rel']

/**
 * Configure DOMPurify to add security attributes to links.
 */
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

/**
 * Configure marked options for secure rendering.
 */
marked.setOptions({
  breaks: true,
  gfm: true
})

/**
 * Renders markdown content to sanitized HTML.
 *
 * @param markdown - The raw markdown string to render.
 * @returns Sanitized HTML string safe for rendering.
 */
export const renderMarkdown = (markdown: string): string => {
  if (!markdown || typeof markdown !== 'string') {
    return ''
  }

  // Parse markdown to HTML
  const rawHtml = marked.parse(markdown) as string

  // Sanitize HTML to prevent XSS
  const sanitizedHtml = DOMPurify.sanitize(rawHtml, {
    ALLOWED_TAGS,
    ALLOWED_ATTR
  })

  return sanitizedHtml
}

/**
 * Checks if a string contains markdown formatting.
 *
 * @param text - The text to check for markdown.
 * @returns True if the text appears to contain markdown.
 */
export const containsMarkdown = (text: string): boolean => {
  if (!text || typeof text !== 'string') {
    return false
  }

  const markdownPatterns = [
    /\*\*.+\*\*/, // Bold
    /\*.+\*/, // Italic
    /~~.+~~/, // Strikethrough
    /^#{1,6}\s/, // Headers
    /^\s*[-*+]\s/, // Lists
    /^\s*\d+\.\s/, // Numbered lists
    /\[.+\]\(.+\)/, // Links
    /^>\s/, // Blockquotes
    /`[^`]+`/, // Inline code
    /```[\s\S]*```/ // Code blocks
  ]

  return markdownPatterns.some((pattern) => pattern.test(text))
}
