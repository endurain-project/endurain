/**
 * Common type definitions for the Endurain application
 *
 * This file serves as a starting point for TypeScript type definitions.
 * As you migrate JavaScript code to TypeScript, add relevant types here.
 */

// Example: API Response wrapper
export interface ApiResponse<T> {
  data: T
  status: number
  message?: string
}

// Add your type definitions below as needed
