<template>
  <div class="container mt-5">
    <div class="row justify-content-center">
      <div class="col-md-6">
        <div class="card">
          <div class="card-body text-center">
            <div v-if="loading">
              <div class="spinner-border text-primary mb-3" role="status">
                <span class="visually-hidden">Loading...</span>
              </div>
              <h4>{{ $t('emailVerification.verifying') }}</h4>
              <p>{{ $t('emailVerification.pleaseWait') }}</p>
            </div>
            
            <div v-else-if="success">
              <div class="text-success mb-3">
                <font-awesome-icon icon="check-circle" size="4x" />
              </div>
              <h4>{{ $t('emailVerification.success') }}</h4>
              <p>{{ message }}</p>
              <router-link to="/login" class="btn btn-primary">
                {{ $t('emailVerification.goToLogin') }}
              </router-link>
            </div>
            
            <div v-else>
              <div class="text-danger mb-3">
                <font-awesome-icon icon="times-circle" size="4x" />
              </div>
              <h4>{{ $t('emailVerification.error') }}</h4>
              <p>{{ message }}</p>
              <router-link to="/login" class="btn btn-secondary">
                {{ $t('emailVerification.backToLogin') }}
              </router-link>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { push } from 'notivue'
import { session } from '@/services/sessionService'

// Variables
const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const loading = ref(true)
const success = ref(false)
const message = ref('')

// Verify email on component mount
onMounted(async () => {
  const token = route.params.token

  if (!token) {
    success.value = false
    message.value = t('emailVerification.invalidToken')
    loading.value = false
    return
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