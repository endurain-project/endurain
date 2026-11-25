import { clsx, type ClassValue } from 'clsx'
import { extendTailwindMerge } from 'tailwind-merge'

/**
 * tailwind-merge reads an unknown `text-*` class as a colour, so it would drop
 * the custom type-scale utilities in `assets/main.css` next to any text colour.
 * Registering them as font sizes keeps them alongside colours and lets them
 * replace other font sizes.
 */
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [
        {
          text: [
            'page-title',
            'card-heading',
            'section-heading',
            'item-title',
            'body',
            'caption',
            'hint',
            'field-error',
            'display',
            'metric',
            'meta',
            'micro',
          ],
        },
      ],
    },
  },
})

/**
 * Merges Tailwind utility classes, resolving conflicts deterministically.
 *
 * @param inputs - Class values to combine (strings, arrays, or conditionals).
 * @returns A single, de-duplicated class string.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
