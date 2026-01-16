<template>
  <div class="col-lg-3 col-md-12">
    <ul
      class="nav nav-pills flex-column mb-auto bg-body-tertiary rounded p-3 shadow-sm"
      id="sidebarNav"
    >
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'dashboard' }"
          @click.prevent="changeActive('dashboard')"
        >
          <font-awesome-icon :icon="['fas', 'dashboard']" />
          <span class="ms-1">{{ $t('healthSideBarComponent.dashboardSection') }}</span>
        </a>
      </li>
      <hr />
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'sleep' }"
          @click.prevent="changeActive('sleep')"
        >
          <font-awesome-icon :icon="['fas', 'bed']" />
          <span class="ms-1">{{ $t('healthSideBarComponent.sleepSection') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'rhr' }"
          @click.prevent="changeActive('rhr')"
        >
          <font-awesome-icon :icon="['fas', 'heart-pulse']" />
          <span class="ms-1">{{ $t('healthSideBarComponent.RHRSection') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'steps' }"
          @click.prevent="changeActive('steps')"
        >
          <font-awesome-icon :icon="['fas', 'shoe-prints']" />
          <span class="ms-1">{{ $t('healthSideBarComponent.stepsSection') }}</span>
        </a>
      </li>
      <li class="nav-item">
        <a
          href="#"
          class="nav-link link-body-emphasis"
          :class="{ active: activeSection === 'weight' }"
          @click.prevent="changeActive('weight')"
        >
          <font-awesome-icon :icon="['fas', 'weight']" />
          <span class="ms-2">{{ $t('healthSideBarComponent.weightSection') }}</span>
        </a>
      </li>
    </ul>
  </div>
</template>

<script setup>
const props = defineProps({
  activeSection: {
    type: String,
    required: true
  }
})

const emit = defineEmits(['updateActiveSection'])

function changeActive(section) {
  emit('updateActiveSection', section)
}
</script>
