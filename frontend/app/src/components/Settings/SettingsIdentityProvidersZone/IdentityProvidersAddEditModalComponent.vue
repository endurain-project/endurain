<template>
  <!-- Modal add/edit identity provider -->
  <div
    class="modal fade"
    :id="action === 'add' ? 'addIdentityProviderModal' : editModalId"
    tabindex="-1"
    :aria-labelledby="action === 'add' ? 'addIdentityProviderModal' : editModalId"
    aria-hidden="true"
  >
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" v-if="action === 'add'">
            {{ $t('identityProvidersAddEditModal.addTitle') }}
          </h1>
          <h1 class="modal-title fs-5" v-else>
            {{ $t('identityProvidersAddEditModal.editTitle') }}
          </h1>
          <button
            type="button"
            class="btn-close"
            data-bs-dismiss="modal"
            aria-label="Close"
            @click="resetForm"
          ></button>
        </div>
        <form @submit.prevent="handleSubmit">
          <div class="modal-body">
            <!-- Template Selection (Add Only) -->
            <div v-if="action === 'add'">
              <label for="providerTemplate" class="form-label"
                ><b>{{ $t('identityProvidersAddEditModal.templateLabel') }}</b></label
              >
              <select
                class="form-select"
                id="providerTemplate"
                v-model="selectedTemplate"
                @change="applyTemplate"
              >
                <option value="">{{ $t('identityProvidersAddEditModal.templateCustom') }}</option>
                <option value="keycloak">Keycloak</option>
                <option value="authentik">Authentik</option>
                <option value="authelia">Authelia</option>
                <option value="google">Google</option>
                <option value="microsoft">Microsoft</option>
              </select>
              <div v-if="templateDescription">
                {{ templateDescription }}
              </div>
            </div>

            <!-- Basic Information -->
            <div>
              <label for="providerName" class="form-label"
                ><b>* {{ $t('identityProvidersAddEditModal.nameLabel') }}</b></label
              >
              <input
                type="text"
                class="form-control"
                id="providerName"
                v-model="formData.name"
                :placeholder="$t('identityProvidersAddEditModal.namePlaceholder')"
                maxlength="100"
                required
              />
            </div>

            <div>
              <label for="providerSlug" class="form-label"
                ><b>* {{ $t('identityProvidersAddEditModal.slugLabel') }}</b></label
              >
              <input
                type="text"
                class="form-control"
                :class="{ 'is-invalid': !isSlugValid }"
                id="providerSlug"
                v-model="formData.slug"
                :placeholder="$t('identityProvidersAddEditModal.slugPlaceholder')"
                maxlength="50"
                pattern="[a-z0-9-]+"
                :disabled="action === 'edit'"
                required
              />
              <div v-if="action === 'add'">
                {{ $t('identityProvidersAddEditModal.slugHelp') }}
              </div>
              <div class="invalid-feedback" v-if="!isSlugValid">
                {{ $t('identityProvidersAddEditModal.slugInvalid') }}
              </div>
            </div>

            <!-- Provider Type -->
            <div>
              <label for="providerType" class="form-label"
                ><b>* {{ $t('identityProvidersAddEditModal.providerTypeLabel') }}</b></label
              >
              <select
                class="form-select"
                id="providerType"
                v-model="formData.provider_type"
                required
              >
                <option value="oidc">OpenID Connect (OIDC)</option>
                <option value="oauth2">OAuth 2.0</option>
              </select>
            </div>

            <!-- OAuth/OIDC Configuration -->
            <div>
              <label for="issuerUrl" class="form-label"
                ><b>* {{ $t('identityProvidersAddEditModal.issuerUrlLabel') }}</b></label
              >
              <input
                type="url"
                class="form-control"
                id="issuerUrl"
                v-model="formData.issuer_url"
                :placeholder="$t('identityProvidersAddEditModal.issuerUrlPlaceholder')"
                maxlength="500"
                required
              />
              <div class="form-text">
                {{ $t('identityProvidersAddEditModal.issuerUrlHelp') }}
              </div>
            </div>

            <div>
              <label for="clientId" class="form-label"
                ><b>* {{ $t('identityProvidersAddEditModal.clientIdLabel') }}</b></label
              >
              <input
                type="text"
                class="form-control"
                id="clientId"
                v-model="formData.client_id"
                :placeholder="$t('identityProvidersAddEditModal.clientIdPlaceholder')"
                maxlength="512"
                required
              />
            </div>

            <div>
              <label for="clientSecret" class="form-label"
                ><b>* {{ $t('identityProvidersAddEditModal.clientSecretLabel') }}</b></label
              >
              <input
                type="password"
                class="form-control"
                id="clientSecret"
                v-model="formData.client_secret"
                :placeholder="
                  action === 'edit'
                    ? $t('identityProvidersAddEditModal.clientSecretPlaceholderEdit')
                    : $t('identityProvidersAddEditModal.clientSecretPlaceholder')
                "
                maxlength="512"
                :required="action === 'add'"
              />
              <div v-if="action === 'edit'">
                {{ $t('identityProvidersAddEditModal.clientSecretHelpEdit') }}
              </div>
            </div>

            <div>
              <label for="scopes" class="form-label"
                ><b>{{ $t('identityProvidersAddEditModal.scopesLabel') }}</b></label
              >
              <input
                type="text"
                class="form-control"
                id="scopes"
                v-model="formData.scopes"
                :placeholder="$t('identityProvidersAddEditModal.scopesPlaceholder')"
                maxlength="500"
              />
              <div class="form-text">
                {{ $t('identityProvidersAddEditModal.scopesHelp') }}
              </div>
            </div>

            <!-- Appearance -->
            <hr />
            <h6>{{ $t('identityProvidersAddEditModal.appearanceSection') }}</h6>

            <div>
              <label for="icon" class="form-label">{{
                $t('identityProvidersAddEditModal.iconLabel')
              }}</label>
              <input
                type="text"
                class="form-control"
                id="icon"
                v-model="formData.icon"
                :placeholder="$t('identityProvidersAddEditModal.iconPlaceholder')"
                maxlength="100"
              />
              <div class="form-text">
                {{ $t('identityProvidersAddEditModal.iconHelp') }}
              </div>
            </div>

            <!-- Options -->
            <hr />
            <h6>{{ $t('identityProvidersAddEditModal.optionsSection') }}</h6>

            <div class="form-check mb-3">
              <input
                class="form-check-input"
                type="checkbox"
                id="enabled"
                v-model="formData.enabled"
              />
              <label class="form-check-label" for="enabled">
                {{ $t('identityProvidersAddEditModal.enabledLabel') }}
              </label>
            </div>

            <div class="form-check mb-3">
              <input
                class="form-check-input"
                type="checkbox"
                id="autoCreateUsers"
                v-model="formData.auto_create_users"
              />
              <label class="form-check-label" for="autoCreateUsers">
                {{ $t('identityProvidersAddEditModal.autoCreateUsersLabel') }}
              </label>
              <div class="form-text">
                {{ $t('identityProvidersAddEditModal.autoCreateUsersHelp') }}
              </div>
            </div>

            <div class="form-check mb-3">
              <input
                class="form-check-input"
                type="checkbox"
                id="syncUserInfo"
                v-model="formData.sync_user_info"
              />
              <label class="form-check-label" for="syncUserInfo">
                {{ $t('identityProvidersAddEditModal.syncUserInfoLabel') }}
              </label>
              <div class="form-text">
                {{ $t('identityProvidersAddEditModal.syncUserInfoHelp') }}
              </div>
            </div>

            <!-- Configuration Notes (Template Mode) -->
            <div v-if="templateNotes" class="alert alert-info mt-3" role="alert">
              <font-awesome-icon :icon="['fas', 'info-circle']" class="me-2" />
              <strong>{{ $t('identityProvidersAddEditModal.configurationNotes') }}</strong>
              <p class="mb-0 mt-2">{{ templateNotes }}</p>
            </div>
          </div>
          <div class="modal-footer">
            <button
              type="button"
              class="btn btn-secondary"
              data-bs-dismiss="modal"
              @click="resetForm"
            >
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button type="submit" class="btn btn-primary" :disabled="isSubmitting">
              <span
                v-if="isSubmitting"
                class="spinner-border spinner-border-sm me-2"
                role="status"
                aria-hidden="true"
              ></span>
              {{
                action === 'add'
                  ? $t('identityProvidersAddEditModal.addButton')
                  : $t('identityProvidersAddEditModal.saveButton')
              }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * IdentityProvidersAddEditModalComponent
 *
 * Modal component for adding or editing identity provider configurations.
 * Supports template-based setup for common providers (Keycloak, Authentik, etc.)
 * and custom manual configuration.
 *
 * @component
 */

// Vue composition API
import { ref, computed, watch, type Ref, type PropType } from 'vue'
// Internationalization
import { useI18n } from 'vue-i18n'
// Bootstrap
import { Modal } from 'bootstrap'
// Notifications
import { push } from 'notivue'
// Services
import { identityProviders } from '@/services/identityProvidersService'
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
  client_secret?: string
  scopes?: string
  auto_create_users?: boolean
  sync_user_info?: boolean
}

/**
 * Template configuration interface
 */
interface TemplateConfig {
  name: string
  provider_type: string
  issuer_url: string
  scopes: string
  icon: string
  description: string
  configuration_notes: string
}

/**
 * Template configurations
 */
const TEMPLATES: Record<string, TemplateConfig> = {
  keycloak: {
    name: 'Keycloak',
    provider_type: 'oidc',
    issuer_url: 'https://{your-keycloak-domain}/realms/{realm}',
    scopes: 'openid profile email',
    icon: 'keycloak',
    description: 'Keycloak - Open Source Identity and Access Management',
    configuration_notes:
      'Replace {your-keycloak-domain} with your Keycloak server domain (e.g., keycloak.example.com) and {realm} with your realm name. Create an OIDC client in Keycloak admin console.'
  },
  authentik: {
    name: 'Authentik',
    provider_type: 'oidc',
    issuer_url: 'https://{your-authentik-domain}/application/o/{slug}/',
    scopes: 'openid profile email',
    icon: 'authentik',
    description: 'Authentik - Open-source Identity Provider',
    configuration_notes:
      'Replace {your-authentik-domain} with your Authentik server domain (e.g., authentik.example.com) and {slug} with your application slug. Create an OAuth2/OIDC provider in Authentik.'
  },
  authelia: {
    name: 'Authelia',
    provider_type: 'oidc',
    issuer_url: 'https://{your-authelia-domain}',
    scopes: 'openid profile email',
    icon: 'authelia',
    description: 'Authelia - Open-source authentication and authorization server',
    configuration_notes:
      'Replace {your-authelia-domain} with your Authelia server domain (e.g., auth.example.com). Configure an OIDC client in your Authelia configuration file.'
  },
  google: {
    name: 'Google',
    provider_type: 'oidc',
    issuer_url: 'https://accounts.google.com',
    scopes: 'openid profile email',
    icon: 'google',
    description: 'Google OAuth 2.0',
    configuration_notes: 'Create OAuth 2.0 credentials in Google Cloud Console.'
  },
  microsoft: {
    name: 'Microsoft',
    provider_type: 'oidc',
    issuer_url: 'https://login.microsoftonline.com/{tenant}/v2.0',
    scopes: 'openid profile email',
    icon: 'microsoft',
    description: 'Microsoft Azure AD / Entra ID',
    configuration_notes:
      "Replace {tenant} with your tenant ID or 'common'. Register an app in Azure Portal."
  }
}

// ============================================================================
// Props & Emits
// ============================================================================

const props = defineProps({
  action: {
    type: String as PropType<'add' | 'edit'>,
    required: true,
    validator: (value: string) => ['add', 'edit'].includes(value)
  },
  provider: {
    type: Object as PropType<IdentityProvider | null>,
    default: null
  }
})

const emit = defineEmits<{
  providerAdded: [provider: IdentityProvider]
  providerUpdated: [provider: IdentityProvider]
}>()

// ============================================================================
// Composables & State
// ============================================================================

const { t } = useI18n()

// ============================================================================
// Component State
// ============================================================================

const selectedTemplate: Ref<string> = ref('')
const isSubmitting: Ref<boolean> = ref(false)

const formData: Ref<{
  name: string
  slug: string
  provider_type: string
  enabled: boolean
  issuer_url: string
  client_id: string
  client_secret: string
  scopes: string
  icon: string
  auto_create_users: boolean
  sync_user_info: boolean
}> = ref({
  name: '',
  slug: '',
  provider_type: 'oidc',
  enabled: false,
  issuer_url: '',
  client_id: '',
  client_secret: '',
  scopes: 'openid profile email',
  icon: '',
  auto_create_users: true,
  sync_user_info: true
})

// ============================================================================
// Computed Properties
// ============================================================================

const editModalId = computed(() => {
  return props.provider
    ? `editIdentityProviderModal${props.provider.id}`
    : 'editIdentityProviderModal'
})

const isSlugValid = computed(() => {
  const slugRegex = /^[a-z0-9-]+$/
  return formData.value.slug === '' || slugRegex.test(formData.value.slug)
})

const templateDescription = computed(() => {
  if (!selectedTemplate.value) return ''
  const template = TEMPLATES[selectedTemplate.value]
  return template ? template.description : ''
})

const templateNotes = computed(() => {
  if (!selectedTemplate.value) return ''
  const template = TEMPLATES[selectedTemplate.value]
  return template ? template.configuration_notes : ''
})

// ============================================================================
// Template Handling
// ============================================================================

/**
 * Apply selected template configuration to form
 */
const applyTemplate = (): void => {
  if (!selectedTemplate.value) {
    return
  }

  const template = TEMPLATES[selectedTemplate.value]
  if (!template) {
    return
  }

  formData.value.name = template.name
  formData.value.slug = template.name.toLowerCase().replace(/\s+/g, '-')
  formData.value.provider_type = template.provider_type
  formData.value.issuer_url = template.issuer_url
  formData.value.scopes = template.scopes
  formData.value.icon = template.icon
}

// ============================================================================
// Form Handling
// ============================================================================

/**
 * Reset form to initial state
 */
const resetForm = (): void => {
  selectedTemplate.value = ''
  formData.value = {
    name: '',
    slug: '',
    provider_type: 'oidc',
    enabled: false,
    issuer_url: '',
    client_id: '',
    client_secret: '',
    scopes: 'openid profile email',
    icon: '',
    auto_create_users: true,
    sync_user_info: true
  }
}

/**
 * Load provider data into form (for edit mode)
 */
const loadProviderData = (): void => {
  if (props.action === 'edit' && props.provider) {
    formData.value = {
      name: props.provider.name || '',
      slug: props.provider.slug || '',
      provider_type: props.provider.provider_type || 'oidc',
      enabled: props.provider.is_enabled || false,
      issuer_url: props.provider.issuer_url || '',
      client_id: props.provider.client_id || '',
      client_secret: '', // Don't load existing secret
      scopes: props.provider.scopes || 'openid profile email',
      icon: props.provider.icon || '',
      auto_create_users: props.provider.auto_create_users ?? true,
      sync_user_info: props.provider.sync_user_info ?? true
    }
  }
}

/**
 * Handle form submission
 */
const handleSubmit = async (): Promise<void> => {
  if (!isSlugValid.value) {
    push.error(t('identityProvidersAddEditModal.slugInvalid'))
    return
  }

  isSubmitting.value = true

  try {
    if (props.action === 'add') {
      await createProvider()
    } else {
      await updateProvider()
    }
  } finally {
    isSubmitting.value = false
  }
}

/**
 * Create new identity provider
 */
const createProvider = async (): Promise<void> => {
  const notification = push.promise(t('identityProvidersAddEditModal.creatingProvider'))

  try {
    const response = await identityProviders.createProvider({
      name: formData.value.name,
      slug: formData.value.slug,
      provider_type: formData.value.provider_type,
      enabled: formData.value.enabled,
      issuer_url: formData.value.issuer_url,
      client_id: formData.value.client_id,
      client_secret: formData.value.client_secret,
      scopes: formData.value.scopes || 'openid profile email',
      icon: formData.value.icon || undefined,
      auto_create_users: formData.value.auto_create_users,
      sync_user_info: formData.value.sync_user_info
    })

    notification.resolve(t('identityProvidersAddEditModal.providerCreated'))
    emit('providerAdded', response)
    closeModal()
    resetForm()
  } catch (error) {
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.CONFLICT) {
      notification.reject(t('identityProvidersAddEditModal.errorSlugExists'))
    } else if (statusCode === HTTP_STATUS.FORBIDDEN) {
      notification.reject(t('identityProvidersAddEditModal.errorForbidden'))
    } else {
      notification.reject(`${t('identityProvidersAddEditModal.errorCreating')} - ${error}`)
    }
  }
}

/**
 * Update existing identity provider
 */
const updateProvider = async (): Promise<void> => {
  if (!props.provider) return

  const notification = push.promise(t('identityProvidersAddEditModal.updatingProvider'))

  try {
    const updateData: any = {
      name: formData.value.name,
      provider_type: formData.value.provider_type,
      enabled: formData.value.enabled,
      issuer_url: formData.value.issuer_url,
      client_id: formData.value.client_id,
      scopes: formData.value.scopes || 'openid profile email',
      icon: formData.value.icon || undefined,
      auto_create_users: formData.value.auto_create_users,
      sync_user_info: formData.value.sync_user_info
    }

    // Only include client_secret if it was changed
    if (formData.value.client_secret) {
      updateData.client_secret = formData.value.client_secret
    }

    const response = await identityProviders.updateProvider(props.provider.id, updateData)

    notification.resolve(t('identityProvidersAddEditModal.providerUpdated'))
    emit('providerUpdated', response)
    closeModal()
    resetForm()
  } catch (error) {
    const statusCode = extractStatusCode(error)
    if (statusCode === HTTP_STATUS.FORBIDDEN) {
      notification.reject(t('identityProvidersAddEditModal.errorForbidden'))
    } else {
      notification.reject(`${t('identityProvidersAddEditModal.errorUpdating')} - ${error}`)
    }
  }
}

/**
 * Close modal programmatically
 */
const closeModal = (): void => {
  const modalId = props.action === 'add' ? 'addIdentityProviderModal' : editModalId.value
  const modalElement = document.getElementById(modalId)
  if (modalElement) {
    const modal = Modal.getInstance(modalElement)
    modal?.hide()
  }
}

// ============================================================================
// Lifecycle & Watchers
// ============================================================================

/**
 * Watch for provider prop changes (edit mode)
 */
watch(
  () => props.provider,
  () => {
    if (props.action === 'edit') {
      loadProviderData()
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.form-control-color {
  width: 100%;
  height: 38px;
}
</style>
