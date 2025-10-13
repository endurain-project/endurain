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
            @click="handleAddProvider"
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
          <div class="mt-3" v-if="providers && providers.length">
            <!-- Title Zone -->
            <span>{{ $t('settingsIdentityProvidersZone.labelNumberOfProviders') }}</span>

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
                @providerDeleted="updateProviderList"
                @providerUpdated="updateProviderInList"
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
import { ref, onMounted, type Ref } from 'vue'
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
import type { IdentityProviderTemplate } from '@/types'

/**
 * Identity Provider interface
 */
interface IdentityProvider {
  id: number
  name: string
  slug: string
  provider_type: string
  icon?: string
  is_enabled: boolean
  issuer_url?: string
  client_id?: string
  authorization_endpoint?: string
  token_endpoint?: string
  userinfo_endpoint?: string
}

// ============================================================================
// Composables & State
// ============================================================================

const { t } = useI18n()

// ============================================================================
// Component State
// ============================================================================

const providers: Ref<IdentityProvider[]> = ref([])
const templates: Ref<IdentityProviderTemplate[]> = ref([])
const isLoading: Ref<boolean> = ref(true)

// ============================================================================
// Data Fetching
// ============================================================================

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
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.FORBIDDEN) {
      push.error(t('settingsIdentityProvidersZone.errorForbidden'))
    } else {
      push.error(`${t('settingsIdentityProvidersZone.errorFetchingProviders')} - ${error}`)
    }
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
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.FORBIDDEN) {
      push.error(t('settingsIdentityProvidersZone.errorForbidden'))
    } else {
      push.error(`${t('settingsIdentityProvidersZone.errorFetchingTemplates')} - ${error}`)
    }
    templates.value = []
  }
}

// ============================================================================
// Action Handlers
// ============================================================================

/**
 * Handle add provider button click
 * Opens modal for adding a new provider
 */
const handleAddProvider = (): void => {
  // Modal is triggered by data-bs-toggle and data-bs-target attributes
}

/**
 * Handle provider added event from modal
 * Adds new provider to the list
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
const updateProviderList = (providerId: number): void => {
  providers.value = providers.value.filter((p) => p.id !== providerId)
}

/**
 * Handle provider updated from list component
 * Updates existing provider in the list
 *
 * @param updatedProvider - Updated provider data
 */
const updateProviderInList = (updatedProvider: IdentityProvider): void => {
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
