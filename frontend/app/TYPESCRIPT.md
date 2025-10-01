# TypeScript Support

This project now supports TypeScript alongside JavaScript, enabling gradual migration and improved developer experience.

## Overview

- **Existing JavaScript files (.js, .vue)** continue to work without any modifications
- **New files** can be written in TypeScript (.ts) or Vue with TypeScript (`<script lang="ts">`)
- Type checking is integrated into the build process

## Getting Started

### Writing TypeScript Files

#### TypeScript Modules (.ts)

Create `.ts` files in the `src/` directory:

```typescript
// src/utils/example.ts
export interface User {
  id: number
  name: string
  email?: string
}

export function greetUser(user: User): string {
  return `Hello, ${user.name}!`
}
```

#### Vue Components with TypeScript

Use `<script lang="ts">` in your Vue components:

```vue
<template>
  <div>{{ message }}</div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue'

export default defineComponent({
  name: 'MyComponent',
  setup() {
    const message = ref<string>('Hello TypeScript!')
    return { message }
  }
})
</script>
```

Or use the Composition API with `<script setup lang="ts">`:

```vue
<template>
  <div>{{ message }}</div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const message = ref<string>('Hello TypeScript!')
</script>
```

### Type Checking

Run type checking manually:

```bash
npm run type-check
```

The build process (`npm run build`) now includes type checking automatically.

### IDE Support

TypeScript configuration is provided via `tsconfig.json`, which enables:
- IntelliSense and autocompletion
- Type checking in your IDE
- Better refactoring support
- Import path resolution for `@/` alias

## Configuration Files

- `tsconfig.json` - Root configuration with project references
- `tsconfig.app.json` - Configuration for application code
- `tsconfig.node.json` - Configuration for Node.js build tools (Vite, Vitest)
- `tsconfig.vitest.json` - Configuration for test files
- `src/env.d.ts` - Vite and global type declarations

## Migration Strategy

TypeScript is **optional** and migration can be done incrementally:

1. Start with new features - write new components/utilities in TypeScript
2. Gradually migrate existing files when making significant changes
3. No immediate action required for existing JavaScript files

## Important Notes

- `allowJs: true` is enabled, so JavaScript and TypeScript can coexist
- Existing JavaScript files will not show type errors
- Type checking is strict for TypeScript files but permissive for JavaScript
