# UI standards

## Principles

- Data-dense, flat and calm: no card shadows (use `border border-border`), no gradients.
- Dark-mode first; numbers are the hero.
- Full detail: `docs/developer-guide/brand-and-ux-guidelines.md`.

## Tokens and styling

- Tokens are defined once in `src/assets/main.css` (`@theme`); never hardcode hex, font sizes or radii (data-viz excepted).
- Use semantic utilities: `bg-background`, `text-foreground`, `text-muted-foreground`, `bg-muted`, `bg-primary`, `text-primary-foreground`.
- Brand accents are for data-viz and semantics only: `text-hr`, `text-effort`, `text-info`, `text-goal`, `bg-brand`.
- Activity colors come from `ActivityTypeBadge`; do not hand-roll them.
- Merge classes with `cn()` (`src/lib/utils.ts`); avoid arbitrary values such as `w-[123px]`.
- Radii: `rounded-card` (12px), `rounded-input` (8px), `rounded-badge` (20px).

## Typography

- Font Inter, weights 400 and 500 only.
- Use semantic type utilities: `text-page-title`, `text-card-heading`, `text-section-heading`, `text-item-title`, `text-body`, `text-caption`, `text-hint`, `text-field-error`; size-only `text-display`, `text-metric`, `text-meta`, `text-micro`.
- Sentence case headings, never Title Case.

## Components

- Compose `src/components/ui/` primitives (shadcn-vue / reka-ui and Endurain's `MetricPill`, `ActivityTypeBadge`, `EmptyState`); do not re-implement them.
- Layout components live in `src/components/layout/`.
- Rich or HTML content renders through `SafeHtml.vue` (DOMPurify).

## Dark mode

- Driven by the `dark` class on `<html>` through `useTheme`.
- Semantic tokens flip automatically; most components need no `dark:` variants.
- Teal on dark surfaces: `dark:text-brand-dark-foreground` / `dark:bg-brand-dark-surface`.

## Accessibility and states

- Interactive controls have an accessible name (`aria-label` or visible text).
- Validation messages use `aria-live="polite"`.
- Full keyboard navigation and visible focus.
- Every async view has loading (`Skeleton`, `aria-busy`), error (with retry) and empty states.
- Responsive from mobile up with `sm:`/`md:`/`lg:` variants.
- Notify through `useToasts`.
