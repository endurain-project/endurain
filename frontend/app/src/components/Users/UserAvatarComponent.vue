<template>
  <img
    :src="userPhotoUrl"
    :alt="altText"
    :width="width"
    :height="height"
    class="rounded-circle"
    :class="{ 'align-top': alignTopValue == 2 }"
    v-if="user && user.photo_path"
  />
  <img
    src="/src/assets/avatar/male1.png"
    alt="Default Female Avatar"
    :width="width"
    :height="height"
    class="rounded-circle"
    :class="{ 'align-top': alignTopValue == 2 }"
    v-else-if="(user && !user.photo_path && user.gender === 1) || !user"
  />
  <img
    src="/src/assets/avatar/female1.png"
    alt="Default Male Avatar"
    :width="width"
    :height="height"
    class="rounded-circle"
    :class="{ 'align-top': alignTopValue == 2 }"
    v-else-if="(user && !user.photo_path && user.gender === 2) || !user"
  />
  <img
    src="/src/assets/avatar/unspecified1.png"
    alt="Default Unspecified Avatar"
    :width="width"
    :height="height"
    class="rounded-circle"
    :class="{ 'align-top': alignTopValue == 2 }"
    v-else
  />
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'

// Props definition
const props = defineProps({
  user: {
    type: [Object, null],
    required: true
  },
  width: {
    type: Number,
    required: true
  },
  height: {
    type: Number,
    required: true
  },
  alignTop: {
    type: Number,
    default: 1,
    required: false
  }
})

// Emits definition
defineEmits(['userDeleted'])

// Reactive variables
const altText = ref('User Avatar')
const userPhotoUrl = ref('')
const alignTopValue = ref(props.alignTop)

function defineUrl() {
  if (props.user?.photo_path) {
    const pathWithoutConfig = props.user.photo_path.split('/').slice(4).join('/')
    userPhotoUrl.value = props.user.photo_path
      ? `${window.env.ENDURAIN_HOST}/${pathWithoutConfig}`
      : null
  }
}

// Lifecycle hooks
onMounted(() => {
  defineUrl()
})

// Watch the user prop for changes.
watch(() => props.user, defineUrl, { immediate: true })
</script>
