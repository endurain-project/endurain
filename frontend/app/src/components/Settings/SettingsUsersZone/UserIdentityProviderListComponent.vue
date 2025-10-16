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
            {{ idp.idp_name }} -
            <span class="fw-lighter">{{ formatProviderType(idp.idp_provider_type) }}</span>
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
        <!-- Delete IDP Link Button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#deleteIdpModal${idp.id}`"
          :aria-label="
            t('userIdentityProviderListComponent.deleteButtonAriaLabel', { provider: idp.idp_name })
          "
        >
          <font-awesome-icon :icon="['fas', 'fa-trash-can']" />
        </a>

        <!-- Delete IDP Modal -->
        <ModalComponent
          :modalId="`deleteIdpModal${idp.id}`"
          :title="t('userIdentityProviderListComponent.modalDeleteTitle')"
          :body="`${t('userIdentityProviderListComponent.modalDeleteBody1')} <b>${idp.idp_name}</b>${t('userIdentityProviderListComponent.modalDeleteBody2')}`"
          :actionButtonType="`danger`"
          :actionButtonText="t('userIdentityProviderListComponent.modalDeleteButton')"
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
 * This component displays a single identity provider (IDP) link for a user in the admin panel.
 * Shows IDP details (name, icon, linked date, last login) and provides delete functionality.
 * Used within the Users List component's IDP tab.
 *
 * Features:
 * - Display IDP metadata (provider name, type, icon)
 * - Show link creation date and last login timestamp
 * - Delete IDP link with modal confirmation
 * - Accessibility: Full ARIA support and keyboard navigation
 * - i18n: Multi-language support
 *
 * @component
 * @example
 * <UserIdentityProviderListComponent
 *   :idp="identityProvider"
 *   :userId="123"
 *   @idpDeleted="handleIdpDeleted"
 * />
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatDateMed, formatTime } from '@/utils/dateTimeUtils'
import { PROVIDER_CUSTOM_LOGO_MAP } from '@/constants/ssoConstants'
import type { UserIdentityProviderEnriched } from '@/types'
import ModalComponent from '@/components/Modals/ModalComponent.vue'

const props = defineProps<{
  /** The identity provider link object with enriched metadata */
  idp: UserIdentityProviderEnriched
  /** The user ID who owns this IDP link */
  userId: number
}>()

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
