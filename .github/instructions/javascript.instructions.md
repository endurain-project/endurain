---
description: 'Vue.js 3 + TypeScript + Bootstrap 5 coding standards, architecture patterns, and pre-commit requirements for the Endurain frontend'
applyTo: '**/*.ts,**/*.js,**/*.vue'
---
# Project Context
- **Framework:** Vue.js 3 with TypeScript support
- **Build Tool:** Vite
- **UI Framework:** Bootstrap 5
- **Additional Libraries:** Chart.js, Leaflet
- **Project Structure:** All frontend code in `frontend/app/src/`

# Development Setup
- **Navigate:** `cd frontend/app`
- **Install dependencies:** `npm install` (≈20 seconds)
- **Dev server:** `npm run dev` (port 5173 or 5174 if occupied)
- **Build:** `npm run build` (≈9 seconds)
- **Format:** `npm run format` (≈5 seconds)

# TypeScript Standards

## Modern Type Inference
- Always use `<script setup lang="ts">` syntax
- Use `ref<T>()` with generic parameter: 
  `const user = ref<User | null>(null)`
- **AVOID** redundant `Ref<T>` annotations: 
  ~~`const user: Ref<User | null> = ref(null)`~~
- Let TypeScript infer types when obvious: 
  `const count = ref(0)` (infers `Ref<number>`)
- Let `computed()` infer return types from callback
- **AVOID** redundant `ComputedRef<T>` annotations

## Type Safety
- Explicit typing for function parameters and return types
- Type imports for complex types: `Router`, 
  `RouteLocationNormalizedLoaded`
- No implicit `any` types
- Centralized imports from `/types/index.ts`

# Documentation Standards

## General Rules

- **Follow JSDoc format** — use standard `/** ... */` block comments.  
- **Always include `@param`, `@returns`, and `@throws`** sections — even when parameters or behavior seem obvious.  
- **Do not include examples** inside docstrings — keep them in external documentation or test cases.  
- **Avoid extended explanations** — use a single summary line followed by concise sections.  
- **Keep comments concise and descriptive** — explain *what* the code does, not *how* it does it.  
- **Use Markdown formatting** (`code`, *italic*, **bold**) inside comments for clarity.  

## Function Documentation

```ts
/**
 * Adds two numbers together.
 *
 * @param a - The first number.
 * @param b - The second number.
 * @returns The sum of `a` and `b`.
 */
function add(a: number, b: number): number {
  return a + b;
}
```

## Class Documentation

Guidelines:

- Document the class itself with a one-line summary.
- Each public method and property should have its own concise JSDoc block.
- Avoid documenting private members unless needed for internal tooling or generated docs.

```ts
/**
 * Represents a user in the system.
 *
 * @remarks
 * Keep descriptions brief; focus on what the class represents or provides.
 */
class User {
  /**
   * Creates a new user instance.
   *
   * @param name - The user’s display name.
   */
  constructor(public name: string) {}

  /**
   * Returns a greeting for the user.
   *
   * @returns A personalized greeting message.
   */
  greet(): string {
    return `Hello, ${this.name}`;
  }
}
```

## Interface / Type Documentation

Guidelines:

- Document each property using @property.
- Avoid repeating type information already in code.
- Keep to one concise sentence per property.

```ts
/**
 * Describes a basic user profile.
 *
 * @property id - Unique identifier for the user.
 * @property name - Full name of the user.
 * @property isAdmin - Whether the user has administrative privileges.
 */
interface UserProfile {
  id: string;
  name: string;
  isAdmin: boolean;
}
```

## Variable / Constant Documentation

Guidelines:

- Use single-line comments for constants or simple variables.
- If a variable is complex or derived, use a full JSDoc block with a one-line summary and @type if helpful.

```ts
/** The maximum number of users allowed in the system. */
const MAX_USERS = 100;
```

# Centralized Architecture

## Validation Utilities (`/utils/validationUtils.ts`)
- `isValidPassword()` - Password validation
- `passwordsMatch()` - Password confirmation
- `isValidEmail()` - RFC 5322 email validation
- `sanitizeInput()` - Input sanitization
- Password strength analysis functions

## Constants (`/constants/httpConstants.ts`)
- `HTTP_STATUS` enum for HTTP status codes
- `extractStatusCode()` for error response parsing
- `QUERY_PARAM_TRUE` for URL parameters

## Type Definitions (`/types/index.ts`)
- `ErrorWithResponse` - Error handling type
- `NotificationType` - Notification types
- `ActionButtonType` - Button action types

## Bootstrap Modals (`/composables/useBootstrapModal.ts`)
- Modal lifecycle management
- Centralized modal control

# UI/UX Standards

## Bootstrap 5
- Use `form-floating` classes for all form inputs
- Follow Bootstrap 5 component patterns
- Maintain consistent spacing and layout

## Accessibility Requirements
- **ARIA labels:** All interactive elements must have 
  `aria-label`
- **Live regions:** Use `aria-live="polite"` for validation 
  messages
- **Keyboard navigation:** Ensure full keyboard navigation
- **Focus management:** Visible and consistent focus outlines
- **Screen readers:** Test with NVDA/VoiceOver

## Responsive Design
- Support mobile, tablet, and desktop viewports
- Test across different screen sizes
- Use Bootstrap responsive utilities

## User Feedback
- Always include loading states for async operations
- Graceful error handling with user-friendly messages
- Clear validation feedback
- Appropriate use of notifications

# Composition API Patterns

- Create reusable composables for shared logic (e.g., `useBootstrapModal`, `useFetch`)
- Use `watch` and `watchEffect` with precise dependency lists
- Clean up side effects in `onUnmounted` or inside `watch` cleanup callbacks
- Use `provide`/`inject` sparingly — only for deep dependency injection where prop drilling is impractical
- Prefer `computed` over `watch` for derived state

# Performance

- Lazy-load components with dynamic imports and `defineAsyncComponent`
- Use `<Suspense>` for async component loading fallbacks
- Apply `v-once` for fully static content and `v-memo` for infrequently changing list items
- Avoid unnecessary watchers; prefer `computed` where possible

# Data Fetching

- Handle loading, error, and success states explicitly in every async operation
- Cancel or ignore stale requests on component unmount or when parameters change
- Use composables to encapsulate fetch logic and keep components clean

# Routing

- Use `useRoute` and `useRouter` inside `<script setup>` for programmatic navigation
- Protect routes with navigation guards (`beforeEnter`, `beforeEach`)
- Use route meta fields for breadcrumbs, auth requirements, and similar cross-cutting data

# Error Handling

- Use the global error handler (`app.config.errorHandler`) for uncaught errors
- Use `errorCaptured` lifecycle hook in components to handle errors from child components locally
- Wrap risky async logic in `try/catch`; always display user-friendly messages
- Never expose raw error objects or stack traces in the UI

# Security (Frontend)

- **Never use `v-html`** with user-controlled data — sanitize with DOMPurify if unavoidable
- Store sensitive tokens in HTTP-only cookies, not `localStorage` or `sessionStorage`
- Use HTTPS for all API requests
- Validate and escape data before rendering in templates or directives

# Reference Implementations (10/10 Quality)

Study these files as templates for new components:

- **`LoginView.vue`** (437 lines) - Authentication with MFA
- **`SignUpView.vue`** (611 lines) - Registration with optional 
  fields
- **`ResetPasswordView.vue`** (~320 lines) - Password reset with 
  token validation
- **`ModalComponentEmailInput.vue`** - RFC 5322 email validation

# Pre-commit Checklist
- ✅ Run `npm run format` before commits
- ✅ Confirm `npm run build` succeeds
- ✅ Ensure `npm run dev` runs without warnings/errors
- ✅ TypeScript types correct (no implicit any)
- ✅ Accessibility attributes verified
- ✅ Uses centralized utilities/constants/types
- ✅ Bootstrap 5 classes applied correctly
- ✅ Manual browser validation complete