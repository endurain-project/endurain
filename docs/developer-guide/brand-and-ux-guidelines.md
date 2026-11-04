# Brand & UX guidelines

This page is the source of truth for Endurain's visual design, the brand
palette, typography, spacing, component primitives, and the UX patterns that
keep screens consistent. Every component built or migrated for the frontend
must follow it.

The design tokens described here are defined once, in
`frontend/src/assets/main.css`, using Tailwind CSS v4 `@theme` blocks. Never
hardcode hex values, font sizes, or radii in components, reference the tokens
(via Tailwind utilities) instead.

!!! info "Clients"
    This doc covers two clients. The **color, typography scale, spacing and
    radii tokens are platform-neutral** and shared by both. Web specifics live
    inline below; the [Mobile](#mobile) section records where mobile mirrors
    the brand and where it deliberately diverges to respect platform
    conventions. The current mobile client is Flutter (mirror in
    `lib/core/theme/`), but these rules apply to any mobile stack (native,
    Flutter, React Native). Bring what makes sense; do not port web-only
    patterns.

!!! note "Stack"
    Vue 3 (`<script setup lang="ts">`) · Tailwind CSS v4 (CSS-first, no
    `tailwind.config.js`) · shadcn-vue / reka-ui primitives · Lucide icons ·
    Chart.js · Leaflet. Avoid PrimeVue / Vuetify / Quasar, they impose a
    design system that conflicts with this one.

## Design philosophy

- **Data density is a feature.** Athletes want pace, HR, power, elevation, and
  time visible at once. Lay data out with clear hierarchy instead of hiding it
  in accordions.
- **Flat and calm.** No gradients, no drop shadows on cards, no decorative
  effects. Hierarchy comes from spacing, weight, and color, not elevation.
- **Dark mode first.** Users check stats after a workout, often outdoors or in
  low light. Every color decision must work on dark backgrounds.
- **Athlete-grade precision.** Numbers are the hero. Units are secondary.
  Labels are tertiary. Never let chrome compete with data.

## Color system

Two layers of tokens cohabit in `main.css`:

1. **Brand `@theme` tokens** (`--color-brand`, `--color-hr`, …), used for
   accents, data-visualization, and activity badges. Exposed as utilities like
   `bg-brand`, `text-hr`, `text-effort`.
2. **shadcn-vue semantic tokens** (`--background`, `--foreground`, `--primary`,
   `--muted-foreground`, …), used for general chrome (surfaces, text,
   borders, buttons). These are what most components consume day to day, and
   they are dark-aware automatically.

!!! tip "Which token do I use?"
    Reach for the **semantic** tokens (`bg-background`, `bg-card`,
    `text-foreground`, `text-muted-foreground`, `bg-primary`, `border`) for
    layout and chrome. Reach for the **brand** tokens (`text-hr`,
    `text-effort`, `text-info`, `text-goal`, `bg-brand`) only for data and
    semantic accents. Never hardcode a hex outside data-viz code.

### Brand - teal

The brand anchor. Reads as "health, outdoors, forward motion".

| Token | Hex | Usage |
|---|---|---|
| `--color-brand-light` | `#E1F5EE` | Badge backgrounds, active nav tints, hover fills |
| `--color-brand` | `#1D9E75` | Primary buttons, active states, chart fills |
| `--color-brand-mid` | `#0F6E56` | Hover on primary button, icon on light tint |
| `--color-brand-dark` | `#085041` | Dark-mode active states |
| `--color-brand-dark-foreground` | `#5DCAA5` | Teal text/icon on dark surfaces |
| `--color-brand-dark-surface` | `#04342C` | Teal active tint on dark surfaces |

### Semantic accents

Each accent maps to a specific data domain. Never swap them.

| Token | Hex | Domain |
|---|---|---|
| `--color-effort` | `#EF9F27` | Effort level, calories, intensity zones |
| `--color-hr` | `#E24B4A` | Heart rate, HR zones 4–5, warnings |
| `--color-info` | `#378ADD` | Distance, speed, informational states |
| `--color-goal` | `#639922` | Goal completion, PRs, streaks |
| `--color-hr-zone-4` | `#F97316` | Heart rate zone 4 in charts |
| `--color-cadence` | `#A855F7` | Cadence stream in charts |
| `--color-temperature` | `#F97316` | Temperature stream in charts |

### Neutrals - warm gray

Slightly warm grays feel more organic and less "SaaS dashboard".

| Token | Hex | Usage |
|---|---|---|
| `--color-surface` | `#F1EFE8` | Page background (light mode) |
| `--color-surface-card` | `#FFFFFF` | Card background (light mode) |
| `--color-ink` | `#2C2C2A` | Primary text (light mode) |

### Activity badge colors

Each sport gets a consistent badge color so activities are recognizable when
scanning a list. Endurain uses **conventional sport colors** (running red,
cycling green, swimming blue), apply them through the
[`ActivityTypeBadge`](#activity-primitives) primitive rather than by hand.

| Activity | Background | Text |
|---|---|---|
| Running | `--color-activity-running-bg` `#FBE9E8` | `--color-activity-running-text` `#B42318` |
| Cycling | `--color-activity-cycling-bg` `#E9F4DC` | `--color-activity-cycling-text` `#466E15` |
| Swimming | `--color-activity-swimming-bg` `#E6F1FB` | `--color-activity-swimming-text` `#185FA5` |
| Hiking | `--color-activity-hiking-bg` `#FAEEDA` | `--color-activity-hiking-text` `#854F0B` |
| Other | `--color-activity-other-bg` `#F1EFE8` | `--color-activity-other-text` `#5F5E5A` |

### shadcn-vue semantic layer

These resolve to the brand palette and flip automatically in dark mode, so a
component written with them needs no per-element `dark:` variant.

| Utility | Light | Dark |
|---|---|---|
| `bg-background` / `text-foreground` | `#F1EFE8` / `#2C2C2A` | `#18181B` / `#F4F4F5` |
| `bg-card` / `text-card-foreground` | `#FFFFFF` / `#2C2C2A` | `#27272A` / `#F4F4F5` |
| `bg-primary` / `text-primary-foreground` | `#1D9E75` / `#FFFFFF` | `#5DCAA5` / `#04342C` |
| `bg-secondary` / `text-secondary-foreground` | `#E1F5EE` / `#0F6E56` | `#04342C` / `#5DCAA5` |
| `text-muted-foreground` | `#888780` | `#A1A1AA` |
| `bg-destructive` | `#E24B4A` | `#E24B4A` |
| `border` | `rgba(0,0,0,0.08)` | `rgba(255,255,255,0.08)` |

## Typography

The UI font is **Inter** (variable), loaded via `@fontsource-variable/inter`
in `src/main.ts` and exposed as `--font-sans`. Use only two weights,
**400 regular** and **500 medium**. Never 600/700; they read as heavy in a
data-dense UI.

Apply type through the **semantic typography utilities** defined in `main.css`
(`@utility`), not ad-hoc `text-[..]` sizes. The role utilities also bake in the
correct token color, so they stay dark-aware:

| Utility | Size / weight | Role |
|---|---|---|
| `text-page-title` | 26px / 500 | Page title |
| `text-card-heading` | 22px / 500 | Card heading |
| `text-section-heading` | 18px / 500 | Section heading |
| `text-item-title` | 15px / 500 | List item / card title |
| `text-body` | 14px / 400, muted | Body / metadata |
| `text-caption` | 11px / 500, uppercase, tracked, muted | Section labels, metric captions |
| `text-hint` | 12px / 400, muted | Unit labels, hints |
| `text-field-error` | 12px / 400, destructive | Form validation messages |

Size-only completions (compose with any weight/color) for recurring roles
across multiple colors:

| Utility | Size | Typical use |
|---|---|---|
| `text-display` | 44px | Hero numbers |
| `text-metric` | 22px | Metric values |
| `text-meta` | 13px | Dense chrome |
| `text-micro` | 11px | Smallest labels |

**Rules**

- Metric values are the hero, make them visually dominant.
- Unit labels (km, bpm, min/km) never compete with the number, keep them
  small and muted (`text-hint`).
- Use `text-caption` for metadata sections (date, sync source, zone label).
- Sentence case everywhere, never Title Case or ALL CAPS in headings.

## Spacing, radii & borders

- **Vertical rhythm** between sections uses `rem` (`1rem`, `1.5rem`, `2rem`);
  component-internal gaps use `px` (`8px`, `12px`, `16px`).
- **Card padding:** `16px` standard, `20px` for detail views.
- **Radii** come from tokens: `rounded-card` (12px), `rounded-input` (8px,
  inputs & buttons), `rounded-badge` (20px). shadcn primitives also use the
  `--radius` scale (`rounded-sm/md/lg/xl`).
- **No box shadows on cards.** Use a hairline border instead,
  `border border-border` (resolves to `rgba(0,0,0,0.08)` light /
  `rgba(255,255,255,0.08)` dark).

## Component primitives

Build UI by composing the shared primitives in
`frontend/src/components/ui/`, do not re-implement them. Notable building
blocks include `button`, `card`, `input`, `label`, `select`, `switch`,
`dialog`, `dropdown-menu`, `tabs`, `popover`, `badge`, plus the Endurain
specific primitives below.

### Activity primitives

**`MetricPill`**, a single summary number (distance, pace, time, HR).

| Prop | Type | Notes |
|---|---|---|
| `label` | `string` | Short uppercase caption, e.g. "Distance" |
| `value` | `string \| number` | Formatted primary value |
| `unit` | `string?` | Optional unit suffix (km, bpm, …) |
| `accent` | `ink \| hr \| effort \| info \| goal \| brand` | Value color (default `ink`) |

```vue
<MetricPill label="Avg pace" :value="'5:12'" unit="/ km" />
<MetricPill label="Avg HR" :value="148" unit="bpm" accent="hr" />
```

- Group 3–4 metric pills in a flex row; never more than 4 per row (wrap or use
  a 2×N grid for detail views).

**`ActivityTypeBadge`**, the sport tag, colored from the activity palette.

| Prop | Type | Notes |
|---|---|---|
| `type` | `running \| cycling \| swimming \| hiking \| other` | Drives the badge color |
| `icon` | `LucideIcon?` | Optional leading icon |

```vue
<ActivityTypeBadge type="running">Running</ActivityTypeBadge>
```

**`EmptyState`**, first-time and filtered empty states (see UX patterns).

### Buttons

- **Primary:** `bg-primary text-primary-foreground` (brand teal).
- **Ghost / secondary:** bordered, `hover:bg-muted`.
- **Destructive:** `text-destructive` with a subtle destructive-tinted border.

Compose these via the `button` primitive rather than re-styling raw `<button>`
elements.

## Dark mode

Dark mode is driven by a `dark` class on `<html>`, toggled by the `useTheme`
composable (`@custom-variant dark` in `main.css`).

- Prefer **semantic tokens** (`bg-background`, `bg-card`, `text-foreground`,
  `text-muted-foreground`, `border`), they flip automatically, so most
  components need **no** `dark:` variants at all.
- Only reach for explicit `dark:` utilities when styling with raw colors. For
  teal on dark surfaces use `dark:text-brand-dark-foreground` and
  `dark:bg-brand-dark-surface` (the base `#1D9E75` is too dark to read there).
- Semantic accents (`hr`, `effort`, `info`, `goal`) keep the same hex in both
  modes, they're designed to work on either background.

## UX patterns

**Activity list**, reverse chronological, infinite scroll (not pagination).
The filter bar uses activity-type badges as toggle filters. Each card shows the
4 core stats inline (no "expand to see stats"); tapping opens a detail view.

**Activity detail**, full-width map at the top (GPX trace, teal polyline),
then a metric grid (2×4 or 2×3 by sport), compact lap-splits table, and
HR/pace/elevation charts below the fold. Gear used links to gear detail.

**Dashboard**, weekly volume histogram at top, a YTD stats row (distance,
time, elevation), then a recent-activities list. Linear scroll, not a draggable
widget grid.

**Empty states**

- First-time: large teal icon, friendly headline, single CTA button.
- Filtered: muted text only, no illustration, e.g. "No running activities
  yet".

**Forms & settings**, labels above inputs (never placeholder-as-label).
Destructive settings (delete account, delete activity) always require a
confirmation dialog. Validation messages use `text-field-error` and
`aria-live="polite"`.

**Charts**, bar charts for weekly volume use a single teal ramp; HR-zone
charts use the green → amber → red ramp; elevation profiles use an `info`-tint
fill with `info` stroke. Remove the Chart.js default legend and build a custom
HTML legend with square swatches. No grid lines unless an axis would be
ambiguous.

## Mobile

Mobile apps share the **brand** (palette, accents, type scale, weights, radii,
spacing) with the web. They do **not** copy the web's chrome: they use native
UI (Material on Android, UIKit/Cupertino on iOS) so each screen feels at home on
its platform. The web `main.css` hex values stay canonical; mobile mirrors the
same hex. The current client is Flutter (mirror in `lib/core/theme/`), but the
guidance below applies to any stack (native, Flutter, React Native).

### What maps directly

| Brand concept | Mobile mapping |
|---|---|
| Brand teal + accents (`hr`/`effort`/`info`/`goal`) | A theme-token file + a brand color helper. Accents identical in both modes; base teal → `#5DCAA5` on dark surfaces. (Flutter: `AppThemeTokens` + `BrandColors`.) |
| shadcn semantic layer | Native color roles (Material `ColorScheme` / iOS semantic colors). Pin dialogs/sheets/menus to the card surface color. |
| Warm neutrals, dark mode | Light/dark themes that follow the system setting. |
| Type roles & sizes (400/500 only) | Native text styles at the same sizes: display 44, page-title 26, card 22, section 18, item 15, body 14, hint 13, caption 11. |
| Radii (card 12 / input 8 / badge 20) | Same radii on cards, inputs, buttons. |
| Hairline borders | Thin card borders; cards stay flat. |

### Where mobile deliberately diverges

- **Font: system, not Inter.** SF (iOS) / Roboto (Android) are the platform
  norm, ship free, and integrate with Dynamic Type. The brand signal is teal +
  the type scale, so mobile keeps the sizes/weights but not the web font.
- **Elevation: flat cards, subtle on transient surfaces.** Cards/app bars are
  flat (web parity), but dialogs/sheets/menus keep a small elevation (depth is
  a real mobile affordance).
- **Native chrome.** Nav bars, dialogs, switches use platform components, not
  web primitives. Brand color/type only.
- **No hover/focus-ring states.** Use pressed/ripple feedback instead.

### Mobile-only rules

- **Tap targets ≥ 48dp.** Don't shrink interactive rows to web density.
- **Resolve brand colors through one platform-neutral helper** so both Android
  and iOS get the same palette.
- **Respect OS text scaling.** Never disable it; verify the 11px caption stays
  legible at large sizes.
- **Theme/status bars** should match the surface.

### Open / shared decisions

- **Dark-mode activity badges** are undefined here — define them in this doc
  first, then all clients mirror. Mobile holds the light tints as constants
  until then.
- Primitives (`MetricPill`, `ActivityTypeBadge`, `EmptyState`) are built per
  platform from the shared tokens, not ported from web markup.

## What to avoid

| ❌ Avoid | ✓ Use instead |
|---|---|
| Box shadows on cards | `border border-border` hairline |
| Gradients anywhere | Flat fills with opacity variants |
| Cool gray neutrals | Warm gray (`surface` / `background` family) |
| Collapsing stats into accordions | Inline metric rows (`MetricPill`) |
| Hardcoded hex / `text-[..]` sizes | Tokens + typography utilities |
| 600 / 700 font weight | 400 / 500 only |
| PrimeVue / Vuetify / Quasar | shadcn-vue + Tailwind utilities |
| Title Case headings | Sentence case always |
| Chart.js default legend | Custom HTML legend with square swatches |
