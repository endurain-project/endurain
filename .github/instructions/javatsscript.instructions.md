---
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

# Component Structure (10 Sections)

All Vue components must follow this exact structure:

1. **Fileoverview JSDoc** - Clear, purposeful component 
   description
2. **Imports** - All dependencies
3. **Composables & Stores** - Router, stores, composables
4. **Reactive State** - ref() declarations
5. **Computed Properties** - computed() declarations
6. **UI Interaction Handlers** - Button clicks, form events
7. **Validation Logic** - Form validation functions
8. **Main Logic** - Core business logic
9. **Lifecycle Hooks** - onMounted, onBeforeUnmount, etc.
10. **Component Definition** - defineExpose if needed

# Documentation Standards
- Each component must include clear, purposeful JSDoc overview
- Document complex logic
- Skip redundant auto-generated comments
- Focus on "why" not "what" for non-obvious code

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
- ✅ Component follows 10-section structure
- ✅ Uses centralized utilities/constants/types
- ✅ Bootstrap 5 classes applied correctly
- ✅ Manual browser validation complete