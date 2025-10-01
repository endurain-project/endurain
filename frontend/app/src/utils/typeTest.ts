// Simple test file to verify TypeScript support
export function greet(name: string): string {
  return `Hello, ${name}!`
}

export interface User {
  id: number
  name: string
  email?: string
}

export const createUser = (id: number, name: string, email?: string): User => {
  return { id, name, email }
}
