<template>
  <!-- back button -->
  <div class="d-lg-none">
    <br />
    <button @click="goBack" type="button" class="w-100 btn btn-primary">
      {{ $t('generalItems.buttonBack') }}
    </button>
  </div>
</template>

<script>
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

export default {
  setup() {
    const router = useRouter()
    const { t } = useI18n()

    function goBack() {
      router.go(-1)
    }

    return {
      goBack,
      t
    }
  }
}
</script>
