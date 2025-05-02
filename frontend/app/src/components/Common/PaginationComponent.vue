<template>
  <nav aria-label="Page navigation" v-if="totalPages > 1">
    <ul class="pagination justify-content-center">
      <li class="page-item" :class="{ disabled: currentPage === 1 }">
        <a
          class="page-link"
          href="#"
          @click.prevent="changePage(currentPage - 1)"
          aria-label="Previous"
        >
          <span aria-hidden="true">&laquo;</span>
        </a>
      </li>

      <!-- Page Numbers (Simplified for now) -->
      <!-- A more robust implementation would handle ellipsis (...) for many pages -->
      <li
        v-for="page in visiblePages"
        :key="page"
        class="page-item"
        :class="{ active: currentPage === page }"
      >
        <a class="page-link" href="#" @click.prevent="changePage(page)">{{ page }}</a>
      </li>

      <li class="page-item" :class="{ disabled: currentPage === totalPages }">
        <a
          class="page-link"
          href="#"
          @click.prevent="changePage(currentPage + 1)"
          aria-label="Next"
        >
          <span aria-hidden="true">&raquo;</span>
        </a>
      </li>
    </ul>
  </nav>
</template>

<script setup>
import { defineProps, defineEmits, computed } from 'vue'

const props = defineProps({
  currentPage: {
    type: Number,
    required: true
  },
  totalPages: {
    type: Number,
    required: true
  },
  // Optional: maxVisibleButtons can be used for more complex pagination UI later
  maxVisibleButtons: {
    type: Number,
    default: 5 // Example: Show 5 page numbers max
  }
})

const emit = defineEmits(['page-changed'])

function changePage(page) {
  if (page >= 1 && page <= props.totalPages && page !== props.currentPage) {
    emit('page-changed', page)
  }
}

// Basic logic for visible pages - can be enhanced later
const visiblePages = computed(() => {
  const pages = []
  let startPage = Math.max(1, props.currentPage - Math.floor(props.maxVisibleButtons / 2))
  let endPage = Math.min(props.totalPages, startPage + props.maxVisibleButtons - 1)

  // Adjust startPage if endPage calculation hits the boundary first
  startPage = Math.max(1, endPage - props.maxVisibleButtons + 1)

  for (let i = startPage; i <= endPage; i++) {
    pages.push(i)
  }
  return pages
})
</script>

<style scoped>
.pagination {
  margin-top: 1rem;
}
.page-link {
  cursor: pointer;
}
</style>
