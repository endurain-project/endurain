<template>
  <div class="markdown-content text-break" v-html="renderedContent" :aria-label="ariaLabel"></div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdownUtils'

/**
 * Props for the MarkdownContentComponent.
 *
 * @property content - The raw markdown content to render (can be null/undefined).
 * @property ariaLabel - Accessibility label for the content.
 */
interface Props {
  content?: string | null
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
  ariaLabel: 'Markdown content'
})

/**
 * Computed property that renders markdown to sanitized HTML.
 * Handles null/undefined content gracefully.
 */
const renderedContent = computed(() => {
  return renderMarkdown(props.content ?? '')
})
</script>

<style scoped>
.markdown-content :deep(h1),
.markdown-content :deep(h2),
.markdown-content :deep(h3),
.markdown-content :deep(h4),
.markdown-content :deep(h5),
.markdown-content :deep(h6) {
  margin-top: 0.5em;
  margin-bottom: 0.25em;
}

.markdown-content :deep(p) {
  margin-bottom: 0.5em;
}

.markdown-content :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-content :deep(ul),
.markdown-content :deep(ol) {
  padding-left: 1.5em;
  margin-bottom: 0.5em;
}

.markdown-content :deep(blockquote) {
  border-left: 3px solid var(--bs-secondary);
  padding-left: 1em;
  margin-left: 0;
  color: var(--bs-secondary);
}

.markdown-content :deep(code) {
  background-color: var(--bs-tertiary-bg);
  padding: 0.125em 0.25em;
  border-radius: 0.25em;
  font-size: 0.875em;
}

.markdown-content :deep(pre) {
  background-color: var(--bs-tertiary-bg);
  padding: 0.75em;
  border-radius: 0.375em;
  overflow-x: auto;
}

.markdown-content :deep(pre code) {
  background-color: transparent;
  padding: 0;
}

.markdown-content :deep(a) {
  color: var(--bs-link-color);
  text-decoration: underline;
}

.markdown-content :deep(a:hover) {
  color: var(--bs-link-hover-color);
}

.markdown-content :deep(table) {
  width: 100%;
  margin-bottom: 0.5em;
  border-collapse: collapse;
}

.markdown-content :deep(th),
.markdown-content :deep(td) {
  border: 1px solid var(--bs-border-color);
  padding: 0.375em 0.75em;
}

.markdown-content :deep(th) {
  background-color: var(--bs-tertiary-bg);
}

.markdown-content :deep(hr) {
  margin: 0.75em 0;
  border-top: 1px solid var(--bs-border-color);
}
</style>
