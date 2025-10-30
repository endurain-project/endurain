<template>
  <img
    :src="avatarSrc"
    :alt="altText"
    :width="width"
    :height="height"
    class="rounded-circle"
    :class="{ 'align-top': alignTopValue == 2 }"
  />
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { getUserDefaultAvatar } from '@/constants/userAvatarConstants'

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

// Computed property for avatar source
const avatarSrc = computed(() => {
  if (props.user?.photo_path && userPhotoUrl.value) {
    return userPhotoUrl.value
  }
  return getUserDefaultAvatar(props.user?.gender)
})

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
