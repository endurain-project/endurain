<template>
  <li
    class="list-group-item bg-body-tertiary rounded px-0"
    :class="{ 'shadow rounded px-3 mb-3': providerDetails }"
  >
    <div class="d-flex justify-content-between">
      <div class="d-flex align-items-center">
        <!-- Provider Icon/Logo -->
        <div class="me-3">
          <img
            :src="getProviderCustomLogo(provider.icon)!"
            :alt="`${provider.name} logo`"
            style="height: 55px; width: 55px; object-fit: contain"
            v-if="
              provider.icon === 'authelia' ||
              provider.icon === 'authentik' ||
              provider.icon === 'casdoor' ||
              provider.icon === 'keycloak' ||
              provider.icon === 'pocketid'
            "
          />
          <img
            :src="provider.icon"
            :alt="`${provider.name} logo`"
            style="height: 55px; width: 55px; object-fit: contain"
            v-else
          />
        </div>

        <!-- Provider Info -->
        <div>
          <div class="fw-bold">
            {{ provider.name }}
          </div>
          <div class="text-muted small">
            <span v-if="provider.provider_type === 'oidc'">{{
              $t('settingsIdentityProvidersZone.oidcType')
            }}</span>
            <span v-else-if="provider.provider_type === 'oauth2'">{{
              $t('settingsIdentityProvidersZone.oauth2Type')
            }}</span>
            <span v-else>{{ provider.provider_type }}</span>
          </div>
        </div>
      </div>

      <div class="d-flex align-items-center">
        <!-- Status Badge -->
        <span
          v-if="provider.enabled"
          class="badge bg-success-subtle border border-success-subtle text-success-emphasis me-2 d-none d-sm-inline"
          :aria-label="$t('settingsIdentityProvidersZone.enabledBadge')"
          >{{ $t('settingsIdentityProvidersZone.enabledBadge') }}</span
        >
        <span
          v-else
          class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis me-2 d-none d-sm-inline"
          :aria-label="$t('settingsIdentityProvidersZone.disabledBadge')"
          >{{ $t('settingsIdentityProvidersZone.disabledBadge') }}</span
        >

        <!-- Toggle Collapse Details -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          data-bs-toggle="collapse"
          :href="`#collapseProviderDetails${provider.id}`"
          role="button"
          aria-expanded="false"
          :aria-controls="`collapseProviderDetails${provider.id}`"
        >
          <font-awesome-icon :icon="['fas', 'caret-down']" v-if="!providerDetails" />
          <font-awesome-icon :icon="['fas', 'caret-up']" v-else />
        </a>

        <!-- Toggle Enable/Disable Button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          @click.prevent="handleToggleProvider"
          :aria-label="
            provider.enabled
              ? $t('settingsIdentityProvidersZone.disableButton')
              : $t('settingsIdentityProvidersZone.enableButton')
          "
        >
          <font-awesome-icon
            :icon="provider.enabled ? ['fas', 'toggle-on'] : ['fas', 'toggle-off']"
          />
        </a>

        <!-- Edit Button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#editIdentityProviderModal${provider.id}`"
          @click="handleEditProvider"
          :aria-label="$t('settingsIdentityProvidersZone.editButton')"
        >
          <font-awesome-icon :icon="['fas', 'edit']" />
        </a>

        <!-- Delete Button -->
        <a
          class="btn btn-link btn-lg link-body-emphasis"
          href="#"
          role="button"
          data-bs-toggle="modal"
          :data-bs-target="`#deleteIdentityProviderModal${provider.id}`"
          :aria-label="$t('settingsIdentityProvidersZone.deleteButton')"
        >
          <font-awesome-icon :icon="['fas', 'trash-can']" />
        </a>
      </div>
    </div>

    <!-- Collapsible Provider Details -->
    <div class="collapse" :id="`collapseProviderDetails${provider.id}`">
      <br />
      <h6>{{ $t('settingsIdentityProvidersZone.providerDetailsTitle') }}</h6>
      <div class="small text-muted">
        <div class="row mb-2">
          <div class="col-sm-3 fw-bold">{{ $t('settingsIdentityProvidersZone.slugLabel') }}:</div>
          <div class="col-sm-9">{{ provider.slug }}</div>
        </div>
        <div class="row mb-2" v-if="provider.issuer_url">
          <div class="col-sm-3 fw-bold">
            {{ $t('settingsIdentityProvidersZone.issuerUrlLabel') }}:
          </div>
          <div class="col-sm-9">{{ provider.issuer_url }}</div>
        </div>
        <div class="row mb-2" v-if="provider.client_id">
          <div class="col-sm-3 fw-bold">
            {{ $t('settingsIdentityProvidersZone.clientIdLabel') }}:
          </div>
          <div class="col-sm-9">{{ provider.client_id }}</div>
        </div>
        <div class="row mb-2" v-if="provider.authorization_endpoint">
          <div class="col-sm-3 fw-bold">
            {{ $t('settingsIdentityProvidersZone.authEndpointLabel') }}:
          </div>
          <div class="col-sm-9">{{ provider.authorization_endpoint }}</div>
        </div>
        <div class="row mb-2" v-if="provider.token_endpoint">
          <div class="col-sm-3 fw-bold">
            {{ $t('settingsIdentityProvidersZone.tokenEndpointLabel') }}:
          </div>
          <div class="col-sm-9">{{ provider.token_endpoint }}</div>
        </div>
        <div class="row mb-2" v-if="provider.userinfo_endpoint">
          <div class="col-sm-3 fw-bold">
            {{ $t('settingsIdentityProvidersZone.userinfoEndpointLabel') }}:
          </div>
          <div class="col-sm-9">{{ provider.userinfo_endpoint }}</div>
        </div>
      </div>
    </div>

    <!-- Edit Identity Provider Modal -->
    <IdentityProvidersAddEditModalComponent
      :action="'edit'"
      :provider="provider"
      :templates="templates"
      @providerUpdated="handleProviderUpdated"
    />

    <!-- Delete Confirmation Modal -->
    <ModalComponent
      :modalId="`deleteIdentityProviderModal${provider.id}`"
      :title="$t('settingsIdentityProvidersZone.deleteModalTitle')"
      :body="$t('settingsIdentityProvidersZone.deleteModalBody', { name: provider.name })"
      actionButtonType="danger"
      :actionButtonText="$t('settingsIdentityProvidersZone.deleteModalConfirm')"
      @submitAction="handleDeleteProvider"
    />
  </li>
</template>

<script setup lang="ts">
// Vue composition API
import { ref, onMounted, type Ref } from 'vue'
// Internationalization
import { useI18n } from 'vue-i18n'
// Notifications
import { push } from 'notivue'
// Services
import { identityProviders } from '@/services/identityProvidersService'
// Components
import ModalComponent from '@/components/Modals/ModalComponent.vue'
import IdentityProvidersAddEditModalComponent from './IdentityProvidersAddEditModalComponent.vue'
// Constants
import { HTTP_STATUS, extractStatusCode } from '@/constants/httpConstants'
import { PROVIDER_CUSTOM_LOGO_MAP } from '@/constants/ssoConstants'
// Types
import type { IdentityProviderTemplate, IdentityProvider } from '@/types'

const props = defineProps<{
  provider: IdentityProvider
  templates: IdentityProviderTemplate[]
}>()

const emit = defineEmits<{
  providerDeleted: [providerId: number]
  providerUpdated: [provider: IdentityProvider]
}>()

const { t } = useI18n()

const providerDetails: Ref<boolean> = ref(false)

const getProviderCustomLogo = (iconName?: string): string | null => {
  if (!iconName) return null
  const logoPath =
    PROVIDER_CUSTOM_LOGO_MAP[iconName.toLowerCase() as keyof typeof PROVIDER_CUSTOM_LOGO_MAP]
  return logoPath || null
}

const handleEditProvider = (): void => {
  // Modal is triggered by data-bs-toggle and data-bs-target attributes
}

const handleProviderUpdated = (updatedProvider: IdentityProvider): void => {
  emit('providerUpdated', updatedProvider)
}

const handleToggleProvider = async (): Promise<void> => {
  const providerToUpodate = props.provider
  providerToUpodate.enabled = !props.provider.enabled
  const notification = push.promise(
    t(
      providerToUpodate.enabled
        ? 'settingsIdentityProvidersZone.enablingProvider'
        : 'settingsIdentityProvidersZone.disablingProvider',
      { name: providerToUpodate.name }
    )
  )

  try {
    await identityProviders.updateProvider(props.provider.id, providerToUpodate)

    // Update local state by emitting to parent
    emit('providerUpdated', { ...props.provider, enabled: providerToUpodate.enabled })

    notification.resolve(
      t(
        providerToUpodate.enabled
          ? 'settingsIdentityProvidersZone.providerEnabled'
          : 'settingsIdentityProvidersZone.providerDisabled',
        { name: providerToUpodate.name }
      )
    )
  } catch (error) {
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.FORBIDDEN) {
      notification.reject(t('settingsIdentityProvidersZone.errorForbidden'))
    } else {
      notification.reject(`${t('settingsIdentityProvidersZone.errorUpdatingProvider')} - ${error}`)
    }
  }
}

const handleDeleteProvider = async (): Promise<void> => {
  const notification = push.promise(
    t('settingsIdentityProvidersZone.deletingProvider', { name: props.provider.name })
  )

  try {
    await identityProviders.deleteProvider(props.provider.id)

    notification.resolve(
      t('settingsIdentityProvidersZone.providerDeleted', { name: props.provider.name })
    )

    emit('providerDeleted', props.provider.id)
  } catch (error) {
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.FORBIDDEN) {
      notification.reject(t('settingsIdentityProvidersZone.errorForbidden'))
    } else {
      notification.reject(`${t('settingsIdentityProvidersZone.errorDeletingProvider')} - ${error}`)
    }
  }
}

onMounted(() => {
  const collapseElement = document.getElementById(`collapseProviderDetails${props.provider.id}`)
  if (collapseElement) {
    collapseElement.addEventListener('show.bs.collapse', () => {
      providerDetails.value = true
    })
    collapseElement.addEventListener('hide.bs.collapse', () => {
      providerDetails.value = false
    })
  }
})
</script>
