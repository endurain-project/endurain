<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <div class="row row-gap-3">
        <div class="col-lg-4 col-md-12">
          <!-- Add Provider Button -->
          <a
            class="w-100 btn btn-primary"
            href="#"
            role="button"
            data-bs-toggle="modal"
            data-bs-target="#addIdentityProviderModal"
            :aria-label="$t('settingsIdentityProvidersZone.addProviderButton')"
            >{{ $t('settingsIdentityProvidersZone.addProviderButton')
            }}{{ $t('generalItems.betaTag') }}</a
          >

          <!-- Add Identity Provider Modal -->
          <IdentityProvidersAddEditModalComponent
            :action="'add'"
            :provider="null"
            :templates="templates"
            @providerAdded="handleProviderAdded"
          />
        </div>
      </div>

      <div>
        <!-- Loading State -->
        <LoadingComponent class="mt-3" v-if="isLoading" />

        <div v-else>
          <!-- Providers List -->
          <div class="mt-3" v-if="hasProviders">
            <span
              >{{ $t('settingsIdentityProvidersZone.labelNumberOfProviders1') }}{{ providers.length
              }}{{ $t('settingsIdentityProvidersZone.labelNumberOfProviders2') }}</span
            >
            <!-- List Zone -->
            <ul
              class="list-group list-group-flush"
              v-for="provider in providers"
              :key="provider.id"
              :provider="provider"
            >
              <IdentityProviderListComponent
                :provider="provider"
                :templates="templates"
                @providerDeleted="handleProviderDeleted"
                @providerUpdated="handleProviderUpdated"
              />
            </ul>
          </div>

          <!-- Empty State -->
          <NoItemsFoundComponents class="mt-3" :show-shadow="false" v-else />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SettingsIdentityProvidersZone Component
 *
 * Admin interface for managing external identity providers (IdPs) for SSO authentication.
 * Allows administrators to:
 * - View all configured identity providers
 * - Add new providers
 * - Edit existing provider configurations
 * - Enable/disable providers
 * - Delete providers
 *
 * @component
 */

// Vue composition API
import { ref, computed, onMounted } from 'vue'
// Internationalization
import { useI18n } from 'vue-i18n'
// Notifications
import { push } from 'notivue'
// Services
import { identityProviders } from '@/services/identityProvidersService'
// Components
import LoadingComponent from '@/components/GeneralComponents/LoadingComponent.vue'
import NoItemsFoundComponents from '@/components/GeneralComponents/NoItemsFoundComponents.vue'
import IdentityProvidersAddEditModalComponent from './SettingsIdentityProvidersZone/IdentityProvidersAddEditModalComponent.vue'
import IdentityProviderListComponent from './SettingsIdentityProvidersZone/IdentityProviderListComponent.vue'
// Constants
import { HTTP_STATUS, extractStatusCode } from '@/constants/httpConstants'
// Types
import type { IdentityProviderTemplate, IdentityProvider } from '@/types'

// ============================================================================
// Composables & State
// ============================================================================

const { t } = useI18n()

// ============================================================================
// Component State
// ============================================================================

const providers = ref<IdentityProvider[]>([])
const templates = ref<IdentityProviderTemplate[]>([])
const isLoading = ref(true)

// ============================================================================
// Computed Properties
// ============================================================================

/**
 * Check if there are any providers configured
 * Used to determine whether to show the list or empty state
 */
const hasProviders = computed(() => providers.value.length > 0)

// ============================================================================
// Data Fetching
// ============================================================================

/**
 * Handle API errors with consistent error messages
 * Centralized error handling for all API calls
 *
 * @param error - Error object from API call
 * @param operationType - Type of operation that failed (providers, templates)
 */
const handleApiError = (error: unknown, operationType: 'providers' | 'templates'): void => {
  const statusCode = extractStatusCode(error)
  if (statusCode === HTTP_STATUS.FORBIDDEN) {
    push.error(t('settingsIdentityProvidersZone.errorForbidden'))
  } else {
    const errorKey =
      operationType === 'providers'
        ? 'settingsIdentityProvidersZone.errorFetchingProviders'
        : 'settingsIdentityProvidersZone.errorFetchingTemplates'
    push.error(`${t(errorKey)} - ${error}`)
  }
}

/**
 * Fetch all identity providers from the API
 * Loads both enabled and disabled providers for admin management
 */
const fetchProviders = async (): Promise<void> => {
  try {
    isLoading.value = true
    const response = await identityProviders.getAllProviders()
    providers.value = response || []
  } catch (error) {
    handleApiError(error, 'providers')
    providers.value = []
  } finally {
    isLoading.value = false
  }
}

/**
 * Fetch identity provider templates from the API
 * Loads pre-configured templates for common providers
 */
const fetchTemplates = async (): Promise<void> => {
  try {
    const response = await identityProviders.getTemplates()
    templates.value = response || []
  } catch (error) {
    handleApiError(error, 'templates')
    templates.value = []
  }
}

// ============================================================================
// Action Handlers
// ============================================================================

/**
 * Handle provider added event from modal
 * Adds new provider to the list and shows success notification
 *
 * @param provider - Newly created provider
 */
const handleProviderAdded = (provider: IdentityProvider): void => {
  providers.value.push(provider)
  push.success(t('settingsIdentityProvidersZone.providerAdded', { name: provider.name }))
}

/**
 * Handle provider deleted from list component
 * Removes provider from the list
 *
 * @param providerId - ID of deleted provider
 */
const handleProviderDeleted = (providerId: number): void => {
  providers.value = providers.value.filter((p) => p.id !== providerId)
}

/**
 * Handle provider updated from list component
 * Updates existing provider in the list with new data
 *
 * @param updatedProvider - Updated provider data
 */
const handleProviderUpdated = (updatedProvider: IdentityProvider): void => {
  const index = providers.value.findIndex((p) => p.id === updatedProvider.id)
  if (index !== -1) {
    providers.value[index] = updatedProvider
  }
}

// ============================================================================
// Lifecycle Hooks
// ============================================================================

/**
 * Component mounted lifecycle hook
 * Fetches all identity providers and templates on component load
 */
onMounted(async () => {
  await Promise.all([fetchProviders(), fetchTemplates()])
})
</script>
