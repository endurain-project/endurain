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
import { signUp as signUpService } from '@/services/signUpService'
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
    await signUpService.verifyEmail({
      token: token
    })
    push.success(t('emailVerification.emailVerified'))
    router.push('/login?verifyEmail=true')
  } catch (error) {
    if (error.toString().includes('404')) {
      push.error(`${t('emailVerification.tokenNotFound')} - ${error}`)
    } else if (error.toString().includes('400')) {
      push.error(`${t('emailVerification.tokenExpired')} - ${error}`)
    } else {
      push.error(`${t('emailVerification.verificationFailed')} - ${error}`)
    }
  }
})
</script>