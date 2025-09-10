<template>
  <div class="text-center">
    <LoadingComponent />
    <br />
    <p>{{ $t('emailVerificationView.title1') }}</p>
    <p>{{ $t('emailVerificationView.title2') }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { session } from '@/services/sessionService'
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'

// Variables
const route = useRoute()
const router = useRouter()
const { t } = useI18n()

// Get token from query params
const token = route.query.token

// Verify email on component mount
onMounted(async () => {
  if (!token) {
    router.push('/login?verifyEmailInvalidLink=true')
  }

  try {
    const response = await session.verifyEmail(token)
    success.value = true
    message.value = response.message || t('emailVerification.verificationSuccess')
    
    push.success(t('emailVerification.emailVerified'))
  } catch (error) {
    success.value = false
    
    if (error.toString().includes('404')) {
      message.value = t('emailVerification.tokenNotFound')
    } else if (error.toString().includes('400')) {
      message.value = t('emailVerification.tokenExpired')
    } else {
      message.value = t('emailVerification.verificationFailed')
    }
    
    push.error(message.value)
  } finally {
    loading.value = false
  }
})
</script>