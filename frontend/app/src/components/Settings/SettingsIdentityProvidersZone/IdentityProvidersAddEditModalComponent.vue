<template>
  <!-- Modal add/edit identity provider -->
  <div
    ref="modalRef"
    class="modal fade"
    :id="action === 'add' ? 'addIdentityProviderModal' : editModalId"
    tabindex="-1"
    :aria-labelledby="headingId"
    aria-hidden="true"
  >
    <div class="modal-dialog modal-lg">
      <div class="modal-content">
        <div class="modal-header">
          <h1 class="modal-title fs-5" :id="headingId" v-if="action === 'add'">
            {{ $t('identityProvidersAddEditModal.addTitle') }}
          </h1>
          <h1 class="modal-title fs-5" :id="headingId" v-else>
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
            <label :for="`providerName_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>* {{ $t('identityProvidersAddEditModal.nameLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              :id="`providerName_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="providerName"
              v-model="formData.name"
              :placeholder="$t('identityProvidersAddEditModal.namePlaceholder')"
              maxlength="100"
              aria-label="Provider name"
              required
            />
            <!-- slug field -->
            <label :for="`providerSlug_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>* {{ $t('identityProvidersAddEditModal.slugLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              :class="{ 'is-invalid': !isSlugValid }"
              :id="`providerSlug_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="providerSlug"
              :aria-describedby="`validationSlugFeedback_${action === 'add' ? 'add' : `edit_${provider?.id}`} slugHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              v-model="formData.slug"
              :placeholder="$t('identityProvidersAddEditModal.slugPlaceholder')"
              maxlength="50"
              pattern="[0-9a-z-]+"
              :disabled="action === 'edit'"
              :aria-invalid="!isSlugValid ? 'true' : 'false'"
              required
            />
            <div
              :id="`slugHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              class="form-text"
              v-if="action === 'add'"
            >
              {{ $t('identityProvidersAddEditModal.slugHelp') }}
            </div>
            <div
              :id="`validationSlugFeedback_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              class="invalid-feedback"
              v-if="!isSlugValid"
            >
              {{ $t('identityProvidersAddEditModal.slugInvalid') }}
            </div>

            <!-- Provider Type -->
            <label :for="`providerType_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>* {{ $t('identityProvidersAddEditModal.providerTypeLabel') }}</b></label
            >
            <select
              class="form-select"
              :id="`providerType_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
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
            <label :for="`issuerUrl_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>* {{ $t('identityProvidersAddEditModal.issuerUrlLabel') }}</b></label
            >
            <input
              type="url"
              class="form-control"
              :id="`issuerUrl_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="issuerUrl"
              :aria-describedby="`issuerUrlHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              v-model="formData.issuer_url"
              :placeholder="$t('identityProvidersAddEditModal.issuerUrlPlaceholder')"
              maxlength="500"
              required
            />
            <div
              :id="`issuerUrlHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              class="form-text"
            >
              {{ $t('identityProvidersAddEditModal.issuerUrlHelp') }}
            </div>

            <!-- client id field -->
            <label :for="`clientId_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>* {{ $t('identityProvidersAddEditModal.clientIdLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              :id="`clientId_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="clientId"
              v-model="formData.client_id"
              :placeholder="$t('identityProvidersAddEditModal.clientIdPlaceholder')"
              maxlength="512"
              aria-label="Client ID"
              required
            />

            <!-- client secret field -->
            <label :for="`clientSecret_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>* {{ $t('identityProvidersAddEditModal.clientSecretLabel') }}</b></label
            >
            <input
              type="password"
              class="form-control"
              :id="`clientSecret_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="clientSecret"
              :aria-describedby="
                action === 'edit' ? `clientSecretHelpText_edit_${provider?.id}` : undefined
              "
              v-model="formData.client_secret"
              :placeholder="
                action === 'edit'
                  ? $t('identityProvidersAddEditModal.clientSecretPlaceholderEdit')
                  : $t('identityProvidersAddEditModal.clientSecretPlaceholder')
              "
              maxlength="512"
              :required="action === 'add'"
            />
            <div
              :id="`clientSecretHelpText_edit_${provider?.id}`"
              class="form-text"
              v-if="action === 'edit'"
            >
              {{ $t('identityProvidersAddEditModal.clientSecretHelpEdit') }}
            </div>

            <!-- scopes field -->
            <label :for="`scopes_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>{{ $t('identityProvidersAddEditModal.scopesLabel') }}</b></label
            >
            <input
              type="text"
              class="form-control"
              :id="`scopes_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="scopes"
              :aria-describedby="`scopesHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              v-model="formData.scopes"
              :placeholder="$t('identityProvidersAddEditModal.scopesPlaceholder')"
              maxlength="500"
            />
            <div
              :id="`scopesHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              class="form-text"
            >
              {{ $t('identityProvidersAddEditModal.scopesHelp') }}
            </div>

            <!-- Appearance -->
            <hr />
            <h6>{{ $t('identityProvidersAddEditModal.appearanceSection') }}</h6>

            <!-- icon field -->
            <label :for="`icon_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>{{ $t('identityProvidersAddEditModal.iconLabel') }}</b></label
            >
            <select
              class="form-select"
              :id="`icon_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="icon"
              v-model="formData.icon"
              aria-label="Provider icon selection"
            >
              <option value="authelia">Authelia</option>
              <option value="authentik">Authentik</option>
              <option value="casdoor">Casdoor</option>
              <option value="keycloak">Keycloak</option>
              <option value="pocketid">Pocket ID</option>
              <option value="custom">{{ $t('identityProvidersAddEditModal.iconCustom') }}</option>
            </select>
            <div
              :id="`iconHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              class="form-text"
            >
              {{ $t('identityProvidersAddEditModal.iconHelp') }}
            </div>

            <!-- custom icon url field (shown only when custom is selected) -->
            <div v-if="formData.icon === 'custom'" class="mt-2">
              <label :for="`customIconUrl_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
                ><b>{{ $t('identityProvidersAddEditModal.customIconUrlLabel') }}</b></label
              >
              <input
                type="url"
                class="form-control"
                :id="`customIconUrl_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
                name="customIconUrl"
                :aria-describedby="`customIconUrlHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
                v-model="formData.custom_icon_url"
                :placeholder="$t('identityProvidersAddEditModal.customIconUrlPlaceholder')"
                maxlength="500"
              />
              <div
                :id="`customIconUrlHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
                class="form-text"
              >
                {{ $t('identityProvidersAddEditModal.customIconUrlHelp') }}
              </div>
            </div>

            <!-- Options -->
            <hr />
            <h6>{{ $t('identityProvidersAddEditModal.optionsSection') }}</h6>

            <!-- enabled select -->
            <label :for="`enabled_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>{{ $t('identityProvidersAddEditModal.enabledLabel') }}</b></label
            >
            <select
              class="form-select"
              :id="`enabled_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="enabled"
              v-model="formData.enabled"
              aria-label="Enable identity provider"
            >
              <option :value="true">
                {{ $t('generalItems.yes') }}
              </option>
              <option :value="false">
                {{ $t('generalItems.no') }}
              </option>
            </select>

            <!-- auto create users select -->
            <label :for="`autoCreateUsers_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>{{ $t('identityProvidersAddEditModal.autoCreateUsersLabel') }}</b></label
            >
            <select
              class="form-select"
              :id="`autoCreateUsers_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="autoCreateUsers"
              :aria-describedby="`autoCreateUsersHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              v-model="formData.auto_create_users"
            >
              <option :value="true">
                {{ $t('generalItems.yes') }}
              </option>
              <option :value="false">
                {{ $t('generalItems.no') }}
              </option>
            </select>
            <div
              :id="`autoCreateUsersHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              class="form-text"
            >
              {{ $t('identityProvidersAddEditModal.autoCreateUsersHelp') }}
            </div>

            <!-- sync user info select -->
            <label :for="`syncUserInfo_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              ><b>{{ $t('identityProvidersAddEditModal.syncUserInfoLabel') }}</b></label
            >
            <select
              class="form-select"
              :id="`syncUserInfo_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              name="syncUserInfo"
              :aria-describedby="`syncUserInfoHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              v-model="formData.sync_user_info"
            >
              <option :value="true">
                {{ $t('generalItems.yes') }}
              </option>
              <option :value="false">
                {{ $t('generalItems.no') }}
              </option>
            </select>
            <div
              :id="`syncUserInfoHelpText_${action === 'add' ? 'add' : `edit_${provider?.id}`}`"
              class="form-text"
            >
              {{ $t('identityProvidersAddEditModal.syncUserInfoHelp') }}
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
// Vue composition API
import { ref, computed, watch, onMounted, onUnmounted, type PropType } from 'vue'
// Internationalization
import { useI18n } from 'vue-i18n'
// Composables
import { useBootstrapModal } from '@/composables/useBootstrapModal'
// Notifications
import { push } from 'notivue'
// Services
import { identityProviders } from '@/services/identityProvidersService'
// Types
import type { IdentityProviderTemplate, IdentityProvider } from '@/types'
// Constants
import { HTTP_STATUS, extractStatusCode } from '@/constants/httpConstants'

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

const { t } = useI18n()
const { initializeModal, hideModal, disposeModal } = useBootstrapModal()

const modalRef = ref<HTMLDivElement | null>(null)
const selectedTemplate = ref('')
const isSubmitting = ref(false)
const headingId = computed(() =>
  props.action === 'add'
    ? 'addIdentityProviderModalTitle'
    : `editIdentityProviderModalTitle_${props.provider?.id ?? 'unknown'}`
)

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
  custom_icon_url: '',
  auto_create_users: true,
  sync_user_info: true
})

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
  if (selectedTemplate.value === '') return ''
  const index = parseInt(selectedTemplate.value)
  const template = props.templates[index]
  return template ? template.description : ''
})

const templateNotes = computed(() => {
  if (selectedTemplate.value === '') return ''
  const index = parseInt(selectedTemplate.value)
  const template = props.templates[index]
  return template ? template.configuration_notes : ''
})

const applyTemplate = (): void => {
  if (selectedTemplate.value === '') {
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
    custom_icon_url: '',
    auto_create_users: true,
    sync_user_info: true
  }
}

const loadProviderData = (): void => {
  if (props.action === 'edit' && props.provider) {
    let iconSelect = null
    let iconCustom = null
    if (
      props.provider.icon !== 'authelia' &&
      props.provider.icon !== 'authentik' &&
      props.provider.icon !== 'casdoor' &&
      props.provider.icon !== 'keycloak' &&
      props.provider.icon !== 'pocketid'
    ) {
      iconSelect = 'custom'
      iconCustom = props.provider.icon
    } else {
      iconSelect = props.provider.icon
      iconCustom = null
    }
    formData.value = {
      name: props.provider.name || '',
      slug: props.provider.slug || '',
      provider_type: props.provider.provider_type || 'oidc',
      enabled: props.provider.enabled || false,
      issuer_url: props.provider.issuer_url || '',
      client_id: props.provider.client_id || '',
      client_secret: '', // Don't load existing secret
      scopes: props.provider.scopes || 'openid profile email',
      icon: iconSelect || '',
      custom_icon_url: iconCustom || '',
      auto_create_users: props.provider.auto_create_users ?? true,
      sync_user_info: props.provider.sync_user_info ?? true
    }
  }
}

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

const createProvider = async (): Promise<void> => {
  const notification = push.promise(t('identityProvidersAddEditModal.creatingProvider'))

  try {
    let icon = null
    if (
      formData.value.icon !== 'authelia' &&
      formData.value.icon !== 'authentik' &&
      formData.value.icon !== 'casdoor' &&
      formData.value.icon !== 'keycloak' &&
      formData.value.icon !== 'pocketid'
    ) {
      icon = formData.value.custom_icon_url
    } else {
      icon = formData.value.icon
    }
    const response = await identityProviders.createProvider({
      name: formData.value.name,
      slug: formData.value.slug.toLowerCase(),
      provider_type: formData.value.provider_type,
      enabled: formData.value.enabled,
      issuer_url: formData.value.issuer_url,
      client_id: formData.value.client_id,
      client_secret: formData.value.client_secret,
      scopes: formData.value.scopes || 'openid profile email',
      icon: icon || null,
      auto_create_users: formData.value.auto_create_users,
      sync_user_info: formData.value.sync_user_info
    })

    notification.resolve(t('identityProvidersAddEditModal.providerCreated'))
    emit('providerAdded', response)
    hideModal()
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

const updateProvider = async (): Promise<void> => {
  if (!props.provider) return

  const notification = push.promise(t('identityProvidersAddEditModal.updatingProvider'))

  try {
    let icon = null
    if (
      formData.value.icon !== 'authelia' &&
      formData.value.icon !== 'authentik' &&
      formData.value.icon !== 'casdoor' &&
      formData.value.icon !== 'keycloak' &&
      formData.value.icon !== 'pocketid'
    ) {
      icon = formData.value.custom_icon_url
    } else {
      icon = formData.value.icon
    }
    const updateData: any = {
      name: formData.value.name,
      slug: formData.value.slug.toLowerCase(),
      provider_type: formData.value.provider_type,
      enabled: formData.value.enabled,
      issuer_url: formData.value.issuer_url,
      client_id: formData.value.client_id,
      scopes: formData.value.scopes || 'openid profile email',
      icon: icon || null,
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
    hideModal()
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

onMounted(async () => {
  await initializeModal(modalRef)
})

onUnmounted(() => {
  disposeModal()
})

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
