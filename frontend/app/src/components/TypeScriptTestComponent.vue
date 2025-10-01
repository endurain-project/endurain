<template>
  <div class="typescript-test">
    <p>{{ message }}</p>
  </div>
</template>

<script lang="ts">
import { defineComponent, ref } from 'vue'
import { greet } from '@/utils/typeTest'

export default defineComponent({
  name: 'TypeScriptTestComponent',
  setup() {
    const message = ref<string>(greet('TypeScript'))

    return {
      message
    }
  }
})
</script>
