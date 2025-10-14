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
            <div v-if="action === 'add'" class="mb-3">
              <label for="providerTemplate"
                ><b>{{ $t('identityProvidersAddEditModal.templateLabel') }}</b></label
              >
              <select
                class="form-select"
                id="providerTemplate"
                v-model="selectedTemplate"
                @change="applyTemplate"
                aria-label="Provider template selection"
              >
                <option value="">{{ $t('identityProvidersAddEditModal.templateCustom') }}</option>
                <option v-for="(template, index) in templates" :key="index" :value="index">
                  {{ template.name }}
                </option>
              </select>
              <div class="form-text" v-if="templateDescription">
                {{ templateDescription }}
              </div>
            </div>

            <!-- Basic Information -->
            <!-- name field -->
            <label for="providerName"
              ><b>* {{ $t('identityProvidersAddEditModal.nameLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              id="providerName"
              name="providerName"
              v-model="formData.name"
              :placeholder="$t('identityProvidersAddEditModal.namePlaceholder')"
              maxlength="100"
              aria-label="Provider name"
              required
            />
            <!-- slug field -->
            <label for="providerSlug"
              ><b>* {{ $t('identityProvidersAddEditModal.slugLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              :class="{ 'is-invalid': !isSlugValid }"
              id="providerSlug"
              name="providerSlug"
              aria-describedby="validationSlugFeedback slugHelpText"
              v-model="formData.slug"
              :placeholder="$t('identityProvidersAddEditModal.slugPlaceholder')"
              maxlength="50"
              pattern="[a-z0-9-]+"
              :disabled="action === 'edit'"
              required
            />
            <div id="slugHelpText" class="form-text" v-if="action === 'add'">
              {{ $t('identityProvidersAddEditModal.slugHelp') }}
            </div>
            <div id="validationSlugFeedback" class="invalid-feedback" v-if="!isSlugValid">
              {{ $t('identityProvidersAddEditModal.slugInvalid') }}
            </div>

            <!-- Provider Type -->
            <label for="providerType"
              ><b>* {{ $t('identityProvidersAddEditModal.providerTypeLabel') }}</b></label
            >
            <select
              class="form-select"
              id="providerType"
              name="providerType"
              v-model="formData.provider_type"
              aria-label="Provider type selection"
              required
            >
              <option value="oidc">OpenID Connect (OIDC)</option>
              <option value="oauth2">OAuth 2.0</option>
            </select>

            <!-- OAuth/OIDC Configuration -->
            <!-- issuer url field -->
            <label for="issuerUrl"
              ><b>* {{ $t('identityProvidersAddEditModal.issuerUrlLabel') }}</b></label
            >
            <input
              type="url"
              class="form-control"
              id="issuerUrl"
              name="issuerUrl"
              aria-describedby="issuerUrlHelpText"
              v-model="formData.issuer_url"
              :placeholder="$t('identityProvidersAddEditModal.issuerUrlPlaceholder')"
              maxlength="500"
              required
            />
            <div id="issuerUrlHelpText" class="form-text">
              {{ $t('identityProvidersAddEditModal.issuerUrlHelp') }}
            </div>

            <!-- client id field -->
            <label for="clientId"
              ><b>* {{ $t('identityProvidersAddEditModal.clientIdLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              id="clientId"
              name="clientId"
              v-model="formData.client_id"
              :placeholder="$t('identityProvidersAddEditModal.clientIdPlaceholder')"
              maxlength="512"
              aria-label="Client ID"
              required
            />

            <!-- client secret field -->
            <label for="clientSecret"
              ><b>* {{ $t('identityProvidersAddEditModal.clientSecretLabel') }}</b></label
            >
            <input
              type="password"
              class="form-control"
              id="clientSecret"
              name="clientSecret"
              aria-describedby="clientSecretHelpText"
              v-model="formData.client_secret"
              :placeholder="
                action === 'edit'
                  ? $t('identityProvidersAddEditModal.clientSecretPlaceholderEdit')
                  : $t('identityProvidersAddEditModal.clientSecretPlaceholder')
              "
              maxlength="512"
              :required="action === 'add'"
            />
            <div id="clientSecretHelpText" class="form-text" v-if="action === 'edit'">
              {{ $t('identityProvidersAddEditModal.clientSecretHelpEdit') }}
            </div>

            <!-- scopes field -->
            <label for="scopes"
              ><b>{{ $t('identityProvidersAddEditModal.scopesLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              id="scopes"
              name="scopes"
              aria-describedby="scopesHelpText"
              v-model="formData.scopes"
              :placeholder="$t('identityProvidersAddEditModal.scopesPlaceholder')"
              maxlength="500"
            />
            <div id="scopesHelpText" class="form-text">
              {{ $t('identityProvidersAddEditModal.scopesHelp') }}
            </div>

            <!-- Appearance -->
            <hr />
            <h6>{{ $t('identityProvidersAddEditModal.appearanceSection') }}</h6>

            <!-- icon field -->
            <label for="icon">{{ $t('identityProvidersAddEditModal.iconLabel') }}</label>
            <input
              type="text"
              class="form-control"
              id="icon"
              name="icon"
              aria-describedby="iconHelpText"
              v-model="formData.icon"
              :placeholder="$t('identityProvidersAddEditModal.iconPlaceholder')"
              maxlength="100"
            />
            <div id="iconHelpText" class="form-text">
              {{ $t('identityProvidersAddEditModal.iconHelp') }}
            </div>

            <!-- Options -->
            <hr />
            <h6>{{ $t('identityProvidersAddEditModal.optionsSection') }}</h6>

            <!-- enabled checkbox -->
            <div class="form-check mb-3">
              <input
                class="form-check-input"
                type="checkbox"
                id="enabled"
                name="enabled"
                v-model="formData.enabled"
                aria-label="Enable identity provider"
              />
              <label class="form-check-label" for="enabled">
                {{ $t('identityProvidersAddEditModal.enabledLabel') }}
              </label>
            </div>

            <!-- auto create users checkbox -->
            <div class="mb-3">
              <div class="form-check">
                <input
                  class="form-check-input"
                  type="checkbox"
                  id="autoCreateUsers"
                  name="autoCreateUsers"
                  aria-describedby="autoCreateUsersHelpText"
                  v-model="formData.auto_create_users"
                />
                <label class="form-check-label" for="autoCreateUsers">
                  {{ $t('identityProvidersAddEditModal.autoCreateUsersLabel') }}
                </label>
              </div>
              <div id="autoCreateUsersHelpText" class="form-text">
                {{ $t('identityProvidersAddEditModal.autoCreateUsersHelp') }}
              </div>
            </div>

            <!-- sync user info checkbox -->
            <div class="mb-3">
              <div class="form-check">
                <input
                  class="form-check-input"
                  type="checkbox"
                  id="syncUserInfo"
                  name="syncUserInfo"
                  aria-describedby="syncUserInfoHelpText"
                  v-model="formData.sync_user_info"
                />
                <label class="form-check-label" for="syncUserInfo">
                  {{ $t('identityProvidersAddEditModal.syncUserInfoLabel') }}
                </label>
              </div>
              <div id="syncUserInfoHelpText" class="form-text">
                {{ $t('identityProvidersAddEditModal.syncUserInfoHelp') }}
              </div>
            </div>

            <!-- Configuration Notes (Template Mode) -->
            <div v-if="templateNotes" class="alert alert-info mt-3" role="alert">
              <font-awesome-icon :icon="['fas', 'info-circle']" class="me-2" />
              <strong>{{ $t('identityProvidersAddEditModal.configurationNotes') }}</strong>
              <p class="mb-0 mt-2">{{ templateNotes }}</p>
            </div>

            <p>* {{ $t('generalItems.requiredField') }}</p>
          </div>
          <div class="modal-footer">
            <button
              type="button"
              class="btn btn-secondary"
              data-bs-dismiss="modal"
              @click="resetForm"
              aria-label="Close modal"
            >
              {{ $t('generalItems.buttonClose') }}
            </button>
            <button
              type="submit"
              class="btn btn-success"
              name="providerSubmit"
              data-bs-dismiss="modal"
              :disabled="isSubmitting || !isSlugValid"
              :aria-label="
                action === 'add'
                  ? $t('identityProvidersAddEditModal.addButton')
                  : $t('identityProvidersAddEditModal.saveButton')
              "
            >
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
import type { ErrorWithResponse, IdentityProviderTemplate, IdentityProvider } from '@/types'
// Constants
import { HTTP_STATUS, extractStatusCode } from '@/constants/httpConstants'

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
  },
  templates: {
    type: Array as PropType<IdentityProviderTemplate[]>,
    default: () => []
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
// Reactive State
// ============================================================================

const selectedTemplate: Ref<string> = ref('')
const isSubmitting: Ref<boolean> = ref(false)

const formData = ref({
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
  if (!selectedTemplate.value || selectedTemplate.value === '') return ''
  const index = parseInt(selectedTemplate.value)
  const template = props.templates[index]
  return template ? template.description : ''
})

const templateNotes = computed(() => {
  if (!selectedTemplate.value || selectedTemplate.value === '') return ''
  const index = parseInt(selectedTemplate.value)
  const template = props.templates[index]
  return template ? template.configuration_notes : ''
})

// ============================================================================
// UI Interaction Handlers
// ============================================================================

/**
 * Apply selected template configuration to form
 */
const applyTemplate = (): void => {
  if (!selectedTemplate.value || selectedTemplate.value === '') {
    return
  }

  const index = parseInt(selectedTemplate.value)
  const template = props.templates[index]
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
// Validation Logic
// ============================================================================

// (Validation is handled via computed properties above)

// ============================================================================
// Main Logic
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
      enabled: props.provider.enabled || false,
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
