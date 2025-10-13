<template>
  <div class="col">
    <div class="bg-body-tertiary rounded p-3 shadow-sm">
      <!-- Header -->
      <a
				class="w-100 btn btn-primary"
				role="button"
        data-bs-toggle="modal"
        data-bs-target="#addIdentityProviderModal"
				@click="handleAddProvider"
				:aria-label="$t('settingsIdentityProvidersZone.addProviderButton')"
				>{{ $t('settingsIdentityProvidersZone.addProviderButton') }}{{ $t('generalItems.betaTag') }}</a
			>

      <!-- Loading State -->
      <LoadingComponent class="mt-3" v-if="isLoading" />

      <!-- Providers List -->
      <ul v-else-if="providers.length > 0" class="list-group list-group-flush">
        <li
          v-for="provider in providers"
          :key="provider.id"
          class="list-group-item d-flex justify-content-between align-items-center bg-body-tertiary px-0"
        >
          <div class="d-flex align-items-center flex-grow-1">
            <!-- Provider Icon/Logo -->
            <div class="me-3">
              <img
                v-if="getProviderCustomLogo(provider.icon)"
                :src="getProviderCustomLogo(provider.icon)!"
                :alt="`${provider.name} logo`"
                style="height: 2rem; width: auto"
              />
              <font-awesome-icon
                v-else-if="provider.icon"
                :icon="getProviderIcon(provider.icon)"
                size="2x"
              />
              <font-awesome-icon v-else :icon="['fas', 'id-card']" size="2x" />
            </div>

            <!-- Provider Info -->
            <div class="flex-grow-1">
              <div class="d-flex align-items-center">
                <div class="fw-bold me-2">{{ provider.name }}</div>
                <span
                  v-if="provider.is_enabled"
                  class="badge bg-success"
                  :aria-label="$t('settingsIdentityProvidersZone.enabledBadge')"
                  >{{ $t('settingsIdentityProvidersZone.enabledBadge') }}</span
                >
                <span
                  v-else
                  class="badge bg-secondary"
                  :aria-label="$t('settingsIdentityProvidersZone.disabledBadge')"
                  >{{ $t('settingsIdentityProvidersZone.disabledBadge') }}</span
                >
              </div>
              <div class="text-muted small">
                <span v-if="provider.provider_type === 'oidc'">{{
                  $t('settingsIdentityProvidersZone.oidcType')
                }}</span>
                <span v-else-if="provider.provider_type === 'oauth2'">{{
                  $t('settingsIdentityProvidersZone.oauth2Type')
                }}</span>
                <span v-else>{{ provider.provider_type }}</span>
                <span class="mx-2">•</span>
                <span>{{ provider.slug }}</span>
              </div>
            </div>
          </div>

          <!-- Action Buttons -->
          <div class="d-flex align-items-center gap-2">
            <!-- Toggle Enable/Disable -->
            <button
              type="button"
              class="btn btn-sm"
              :class="provider.is_enabled ? 'btn-outline-warning' : 'btn-outline-success'"
              @click="handleToggleProvider(provider)"
              :aria-label="
                provider.is_enabled
                  ? $t('settingsIdentityProvidersZone.disableButton')
                  : $t('settingsIdentityProvidersZone.enableButton')
              "
            >
              <font-awesome-icon
                :icon="provider.is_enabled ? ['fas', 'toggle-on'] : ['fas', 'toggle-off']"
                class="me-1"
              />
              {{
                provider.is_enabled
                  ? $t('settingsIdentityProvidersZone.disableButton')
                  : $t('settingsIdentityProvidersZone.enableButton')
              }}
            </button>

            <!-- Edit Button -->
            <button
              type="button"
              class="btn btn-sm btn-outline-primary"
              data-bs-toggle="modal"
              :data-bs-target="`#editIdentityProviderModal${provider.id}`"
              @click="handleEditProvider(provider)"
              :aria-label="$t('settingsIdentityProvidersZone.editButton')"
            >
              <font-awesome-icon :icon="['fas', 'edit']" />
            </button>

            <!-- Delete Button -->
            <button
              type="button"
              class="btn btn-sm btn-outline-danger"
              data-bs-toggle="modal"
              data-bs-target="#deleteIdentityProviderModal"
              @click="handleDeleteProvider(provider)"
              :aria-label="$t('settingsIdentityProvidersZone.deleteButton')"
            >
              <font-awesome-icon :icon="['fas', 'trash']" />
            </button>
          </div>
        </li>
      </ul>

      <!-- Empty State -->
      <NoItemsFoundComponents :show-shadow="false" v-else />

      <!-- Info Alert -->
      <div v-if="providers.length > 0" class="alert alert-info mt-3" role="alert">
        <font-awesome-icon :icon="['fas', 'info-circle']" />
        <span class="ms-2">{{ $t('settingsIdentityProvidersZone.infoAlert') }}</span>
      </div>
    </div>

    <!-- Add/Edit Identity Provider Modal -->
    <IdentityProvidersAddEditModalComponent
      :action="modalAction"
      :provider="selectedProvider"
      @providerAdded="handleProviderAdded"
      @providerUpdated="handleProviderUpdated"
    />

    <!-- Delete Confirmation Modal -->
    <ModalComponent
      modalId="deleteIdentityProviderModal"
      :title="$t('settingsIdentityProvidersZone.deleteModalTitle')"
      :body="
        selectedProvider
          ? $t('settingsIdentityProvidersZone.deleteModalBody', { name: selectedProvider.name })
          : ''
      "
      actionButtonType="danger"
      :actionButtonText="$t('settingsIdentityProvidersZone.deleteModalConfirm')"
      @submitAction="confirmDeleteProvider"
    />
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
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import IdentityProvidersAddEditModalComponent from './SettingsIdentityProvidersZone/IdentityProvidersAddEditModalComponent.vue'

// Types
import type { ErrorWithResponse } from '@/types'
// Constants
import { HTTP_STATUS, extractStatusCode } from '@/constants/httpConstants'

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

/**
 * Icon mapping for SSO providers
 * Maps provider icon names to FontAwesome icon arrays
 */
const PROVIDER_ICON_MAP: Record<string, [string, string]> = {
  google: ['fab', 'google'],
  microsoft: ['fab', 'microsoft'],
  github: ['fab', 'github'],
  gitlab: ['fab', 'gitlab'],
  okta: ['fas', 'id-card'],
  auth0: ['fas', 'lock'],
  keycloak: ['fas', 'key'],
  authentik: ['fas', 'shield-halved'],
  authelia: ['fas', 'shield-alt'],
  default: ['fas', 'id-card']
} as const

/**
 * Custom logo mapping for SSO providers
 * Maps provider icon names to image paths for custom logos
 */
const PROVIDER_CUSTOM_LOGO_MAP: Record<string, string> = {
  keycloak: '/src/assets/sso/keycloak.svg',
  authentik: '/src/assets/sso/authentik.svg',
  authelia: '/src/assets/sso/authelia.svg'
} as const

// ============================================================================
// Composables & State
// ============================================================================

const { t } = useI18n()

// ============================================================================
// Component State
// ============================================================================

const providers: Ref<IdentityProvider[]> = ref([])
const isLoading: Ref<boolean> = ref(true)
const selectedProvider: Ref<IdentityProvider | null> = ref(null)
const modalAction: Ref<'add' | 'edit'> = ref('add')

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

// ============================================================================
// Icon & Logo Helpers
// ============================================================================

/**
 * Check if a provider has a custom logo
 * Returns the logo path if available
 *
 * @param iconName - Provider icon name
 * @returns Custom logo path or null
 */
const getProviderCustomLogo = (iconName?: string): string | null => {
  if (!iconName) return null
  const logoPath =
    PROVIDER_CUSTOM_LOGO_MAP[iconName.toLowerCase() as keyof typeof PROVIDER_CUSTOM_LOGO_MAP]
  return logoPath || null
}

/**
 * Get FontAwesome icon for a provider
 * Maps provider icon names to icon arrays
 * Only used when custom logo is not available
 *
 * @param iconName - Provider icon name
 * @returns FontAwesome icon array
 */
const getProviderIcon = (iconName?: string): [string, string] => {
  if (!iconName) return PROVIDER_ICON_MAP.default as [string, string]
  const icon = PROVIDER_ICON_MAP[iconName.toLowerCase() as keyof typeof PROVIDER_ICON_MAP]
  return (icon || PROVIDER_ICON_MAP.default) as [string, string]
}

// ============================================================================
// Action Handlers
// ============================================================================

/**
 * Handle add provider button click
 * Opens modal for adding a new provider
 */
const handleAddProvider = (): void => {
  modalAction.value = 'add'
  selectedProvider.value = null
  // Modal is triggered by data-bs-toggle and data-bs-target attributes
}

/**
 * Handle edit provider button click
 * Opens modal with existing provider data
 *
 * @param provider - Provider to edit
 */
const handleEditProvider = (provider: IdentityProvider): void => {
  modalAction.value = 'edit'
  selectedProvider.value = provider
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
}

/**
 * Handle provider updated event from modal
 * Updates existing provider in the list
 *
 * @param updatedProvider - Updated provider data
 */
const handleProviderUpdated = (updatedProvider: IdentityProvider): void => {
  const index = providers.value.findIndex((p) => p.id === updatedProvider.id)
  if (index !== -1) {
    providers.value[index] = updatedProvider
  }
}

/**
 * Handle toggle enable/disable provider
 * Updates provider enabled status
 *
 * @param provider - Provider to toggle
 */
const handleToggleProvider = async (provider: IdentityProvider): Promise<void> => {
  const newStatus = !provider.is_enabled
  const notification = push.promise(
    t(
      newStatus
        ? 'settingsIdentityProvidersZone.enablingProvider'
        : 'settingsIdentityProvidersZone.disablingProvider',
      { name: provider.name }
    )
  )

  try {
    await identityProviders.updateProvider(provider.id, {
      is_enabled: newStatus
    })

    // Update local state
    provider.is_enabled = newStatus

    notification.resolve(
      t(
        newStatus
          ? 'settingsIdentityProvidersZone.providerEnabled'
          : 'settingsIdentityProvidersZone.providerDisabled',
        { name: provider.name }
      )
    )
  } catch (error) {
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.FORBIDDEN) {
      notification.reject(t('settingsIdentityProvidersZone.errorForbidden'))
    } else {
      notification.reject(
        `${t('settingsIdentityProvidersZone.errorUpdatingProvider')} - ${error}`
      )
    }
  }
}

/**
 * Handle delete provider button click
 * Shows confirmation modal before deleting
 *
 * @param provider - Provider to delete
 */
const handleDeleteProvider = (provider: IdentityProvider): void => {
  selectedProvider.value = provider
  // Modal is triggered by data-bs-toggle and data-bs-target attributes
}

/**
 * Confirm and execute provider deletion
 * Removes provider from database and updates UI
 */
const confirmDeleteProvider = async (): Promise<void> => {
  if (!selectedProvider.value) return

  const provider = selectedProvider.value
  const notification = push.promise(
    t('settingsIdentityProvidersZone.deletingProvider', { name: provider.name })
  )

  try {
    await identityProviders.deleteProvider(provider.id)

    // Remove from local state
    providers.value = providers.value.filter((p) => p.id !== provider.id)

    notification.resolve(
      t('settingsIdentityProvidersZone.providerDeleted', { name: provider.name })
    )
    selectedProvider.value = null
  } catch (error) {
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.FORBIDDEN) {
      notification.reject(t('settingsIdentityProvidersZone.errorForbidden'))
    } else {
      notification.reject(`${t('settingsIdentityProvidersZone.errorDeletingProvider')} - ${error}`)
    }
  }
}

// ============================================================================
// Lifecycle Hooks
// ============================================================================

/**
 * Component mounted lifecycle hook
 * Fetches all identity providers on component load
 */
onMounted(async () => {
  await fetchProviders()
})
</script>
