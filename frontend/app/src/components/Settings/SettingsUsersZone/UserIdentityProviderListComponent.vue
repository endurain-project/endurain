<template>
  <li class="list-group-item bg-body-tertiary rounded border-0">
    <div class="d-flex justify-content-between">
      <div class="d-flex align-items-center">
        <!-- IDP Icon/Logo -->
        <div class="me-3">
          <img
            v-if="getProviderCustomLogo(idp.idp_icon)"
            :src="getProviderCustomLogo(idp.idp_icon)!"
            :alt="`${idp.idp_name} logo`"
            style="height: 55px; width: 55px; object-fit: contain"
          />
          <font-awesome-icon
            v-else
            :icon="['fas', 'circle-question']"
            size="3x"
            :aria-label="t('userIdentityProviderListComponent.unknownProviderIcon')"
          />
        </div>

        <!-- IDP Details -->
        <div>
          <div class="fw-bold">
            {{ idp.idp_name }}
            <span v-if="showProviderType" class="fw-lighter">
              - {{ formatProviderType(idp.idp_provider_type) }}</span
            >
          </div>
          <div class="text-muted small">
            <span :aria-label="t('userIdentityProviderListComponent.linkedAtLabel')">
              {{ $t('userIdentityProviderListComponent.linkedAt') }}:
              {{ formatTime(idp.linked_at) }} - {{ formatDateMed(idp.linked_at) }}
            </span>
          </div>
          <div class="text-muted small" v-if="idp.last_login">
            <span :aria-label="t('userIdentityProviderListComponent.lastLoginLabel')">
              {{ $t('userIdentityProviderListComponent.lastLogin') }}:
              {{ formatTime(idp.last_login) }} - {{ formatDateMed(idp.last_login) }}
            </span>
          </div>
          <div class="text-muted small" v-else>
            <span :aria-label="t('userIdentityProviderListComponent.neverUsedLabel')">
              {{ $t('userIdentityProviderListComponent.neverUsed') }}
            </span>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="d-flex align-items-center">
        <!-- Delete/Unlink IDP Link Button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#idpActionModal${idp.id}`"
          :aria-label="actionButtonAriaLabel"
        >
          <font-awesome-icon :icon="actionIconName" />
        </a>

        <!-- Delete/Unlink IDP Modal -->
        <ModalComponent
          :modalId="`idpActionModal${idp.id}`"
          :title="modalTitle"
          :body="modalBody"
          :actionButtonType="`danger`"
          :actionButtonText="modalButtonText"
          @submitAction="submitDeleteIdp"
        />
      </div>
    </div>
  </li>
</template>

<script setup lang="ts">
/**
 * @fileoverview UserIdentityProviderListComponent - Display and manage user external authentication provider links
 *
 * This component displays a single identity provider (IDP) link for a user.
 * Shows IDP details (name, icon, linked date, last login) and provides delete/unlink functionality.
 * Used in both admin panel (Users List IDP tab) and user settings (Linked Accounts section).
 *
 * Features:
 * - Display IDP metadata (provider name, type, icon)
 * - Show link creation date and last login timestamp
 * - Delete/unlink IDP link with modal confirmation
 * - Context-aware: trash icon (admin) or unlink icon (self-service)
 * - Optional provider type display
 * - Accessibility: Full ARIA support and keyboard navigation
 * - i18n: Multi-language support
 *
 * @component
 * @example
 * // Admin context (default)
 * <UserIdentityProviderListComponent
 *   :idp="identityProvider"
 *   :userId="123"
 *   @idpDeleted="handleIdpDeleted"
 * />
 *
 * @example
 * // User settings context
 * <UserIdentityProviderListComponent
 *   :idp="identityProvider"
 *   :userId="currentUser.id"
 *   actionIcon="unlink"
 *   :showProviderType="false"
 *   @idpDeleted="handleUnlinkAccount"
 * />
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatDateMed, formatTime } from '@/utils/dateTimeUtils'
import { PROVIDER_CUSTOM_LOGO_MAP } from '@/constants/ssoConstants'
import type { UserIdentityProviderEnriched } from '@/types'
import ModalComponent from '@/components/Modals/ModalComponent.vue'

const props = withDefaults(
  defineProps<{
    /** The identity provider link object with enriched metadata */
    idp: UserIdentityProviderEnriched
    /** The user ID who owns this IDP link */
    userId: number
    /** Action icon type: 'trash' for admin delete, 'unlink' for user self-service */
    actionIcon?: 'trash' | 'unlink'
    /** Whether to show the provider type (e.g., "OpenID Connect") */
    showProviderType?: boolean
  }>(),
  {
    actionIcon: 'trash',
    showProviderType: true
  }
)

const emit = defineEmits<{
  /** Emitted when IDP link is successfully deleted */
  idpDeleted: [idpId: number]
}>()

const { t } = useI18n()

/**
 * Icon & Logo Helpers
 */

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
 * Formats the provider type for display
 * Converts technical type names to user-friendly labels
 *
 * @param type - Provider type (oidc, oauth2, saml)
 * @returns Formatted provider type string
 */
const formatProviderType = computed(() => {
  return (type: string): string => {
    switch (type?.toLowerCase()) {
      case 'oidc':
        return 'OpenID Connect'
      case 'oauth2':
        return 'OAuth 2.0'
      case 'saml':
        return 'SAML'
      default:
        return type || 'Unknown'
    }
  }
})

/**
 * UI State & Computed Properties
 */

/**
 * Action icon for delete/unlink button
 * Returns FontAwesome icon array based on actionIcon prop
 */
const actionIconName = computed(() =>
  props.actionIcon === 'unlink' ? ['fas', 'unlink'] : ['fas', 'fa-trash-can']
)

/**
 * ARIA label for action button
 * Context-aware label for accessibility
 */
const actionButtonAriaLabel = computed(() => {
  const action = props.actionIcon === 'unlink' ? 'Unlink' : 'Delete'
  return `${action} ${props.idp.idp_name}`
})

/**
 * Modal title text
 * Context-aware title based on action type
 */
const modalTitle = computed(() =>
  props.actionIcon === 'unlink'
    ? t('settingsSecurityZone.unlinkModalTitle')
    : t('userIdentityProviderListComponent.modalDeleteTitle')
)

/**
 * Modal body text
 * Context-aware confirmation message
 */
const modalBody = computed(() =>
  props.actionIcon === 'unlink'
    ? t('settingsSecurityZone.unlinkModalConfirmation', { providerName: props.idp.idp_name })
    : `${t('userIdentityProviderListComponent.modalDeleteBody1')} <b>${props.idp.idp_name}</b>${t('userIdentityProviderListComponent.modalDeleteBody2')}`
)

/**
 * Modal button text
 * Context-aware action button label
 */
const modalButtonText = computed(() =>
  props.actionIcon === 'unlink'
    ? t('settingsSecurityZone.unlinkAccountButton')
    : t('userIdentityProviderListComponent.modalDeleteButton')
)

/**
 * Main Logic
 */

/**
 * Handles IDP deletion modal submission
 * Emits idpDeleted event to parent component for actual API call
 *
 * Security:
 * - Actual deletion is performed by parent component
 * - Admin-only operation enforced by backend
 * - Audit logging handled by backend
 *
 * @emits idpDeleted - Passes IDP ID to parent for deletion
 */
async function submitDeleteIdp(): Promise<void> {
  emit('idpDeleted', props.idp.idp_id)
}
</script>
