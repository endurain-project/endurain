<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  IdentityProvider,
  IdentityProviderInput,
  IdentityProviderTemplate,
} from '@/features/identityProviders/types'

import { Alert } from '@/components/ui/alert'
import { FormDialog } from '@/components/ui/form-dialog'
import { FormField } from '@/components/ui/form-field'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { useForm } from '@/composables/useForm'
import ProviderIconPicker from '@/features/identityProviders/components/ProviderIconPicker.vue'
import PasswordInput from '@/features/security/components/PasswordInput.vue'
import { HttpError } from '@/services/http'
import {
  ICON_ACCEPTED_TYPES,
  ICON_MAX_BYTES,
  UPLOADED_ICON,
  isBuiltinProviderIcon,
  resolveProviderLogo,
} from '@/features/identityProviders/utils/providerIcon'
import { compose, maxLength, pattern, required } from '@/utils/validators'
import {
  useCreateIdentityProviderMutation,
  useDeleteIdentityProviderIconMutation,
  useUpdateIdentityProviderMutation,
  useUploadIdentityProviderIconMutation,
} from '@/features/identityProviders/composables/useIdentityProviders'

const open = defineModel<boolean>('open', { required: true })

const props = withDefaults(
  defineProps<{
    /** The provider being edited, or `null`/absent when adding a new one. */
    provider?: IdentityProvider | null
    /** Presets offered in the add form's template selector. */
    templates?: IdentityProviderTemplate[]
  }>(),
  { provider: null, templates: () => [] },
)

const emit = defineEmits<{
  success: [message: string]
  error: [message: string]
}>()

const { t } = useI18n()

const createMutation = useCreateIdentityProviderMutation()
const updateMutation = useUpdateIdentityProviderMutation()
const uploadIconMutation = useUploadIdentityProviderIconMutation()
const deleteIconMutation = useDeleteIdentityProviderIconMutation()

const DEFAULT_SCOPES = 'openid profile email'

/** The add/edit form shape; `icon` is a built-in key, `custom`, `uploaded`, or empty (none). */
interface ProviderFormValues {
  name: string
  slug: string
  providerType: string
  enabled: boolean
  issuerUrl: string
  clientId: string
  clientSecret: string
  scopes: string
  icon: string
  autoCreateUsers: boolean
  syncUserInfo: boolean
}

/** The pristine values used for "add" and as the reset baseline. */
function defaultValues(): ProviderFormValues {
  return {
    name: '',
    slug: '',
    providerType: 'oidc',
    enabled: false,
    issuerUrl: '',
    clientId: '',
    clientSecret: '',
    scopes: DEFAULT_SCOPES,
    icon: '',
    autoCreateUsers: true,
    syncUserInfo: true,
  }
}

/**
 * Derives a URL-safe slug from a display name (lowercase, spaces to hyphens,
 * invalid characters dropped) so it satisfies the backend's slug pattern.
 *
 * @param name - The provider display name.
 * @returns A slug matching `^[a-z0-9-]+$`.
 */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
}

/**
 * Builds the clean provider input from the form values. The icon resolves to
 * the built-in key or `null` (an uploaded image is stored separately); an empty secret becomes `null`
 * so an edit keeps the stored secret.
 *
 * @param values - The validated form values.
 * @returns The provider input for the create/update mutation.
 */
function buildInput(values: ProviderFormValues): IdentityProviderInput {
  // An uploaded image is stored separately and shown in place of `icon`, so the column stays empty.
  const icon = values.icon === UPLOADED_ICON ? null : values.icon || null
  return {
    name: values.name.trim(),
    slug: values.slug.trim().toLowerCase(),
    providerType: values.providerType,
    enabled: values.enabled,
    issuerUrl: values.issuerUrl.trim() || null,
    clientId: values.clientId.trim() || null,
    clientSecret: values.clientSecret || null,
    scopes: values.scopes.trim() || DEFAULT_SCOPES,
    icon,
    autoCreateUsers: values.autoCreateUsers,
    syncUserInfo: values.syncUserInfo,
  }
}

/**
 * Applies the chosen icon source to the uploaded image: uploads the picked file,
 * or removes the stored image when another source replaced it.
 *
 * @param id - The saved provider's id.
 * @param values - The validated form values.
 * @returns Whether the uploaded image is now as chosen.
 */
async function syncUploadedIcon(id: number, values: ProviderFormValues): Promise<boolean> {
  try {
    if (values.icon === UPLOADED_ICON) {
      if (iconFile.value) {
        await uploadIconMutation.mutateAsync({ id, file: iconFile.value })
      }
    } else if (props.provider?.iconUploaded) {
      await deleteIconMutation.mutateAsync(id)
    }
    return true
  } catch {
    return false
  }
}

/**
 * Persists the provider, emitting the outcome to the parent and closing on
 * success. A duplicate slug (`409`) is surfaced as a specific message; other
 * failures fall back to a generic one so the dialog stays open for correction.
 *
 * @param values - The validated form values.
 */
async function submitForm(values: ProviderFormValues): Promise<void> {
  const input = buildInput(values)
  try {
    const saved = props.provider
      ? await updateMutation.mutateAsync({
          id: props.provider.id,
          input,
          version: props.provider.version,
        })
      : await createMutation.mutateAsync(input)
    // The provider is saved by now, so an icon failure is reported without keeping the dialog open:
    // a retry of the create would only hit the slug conflict.
    const iconSaved = await syncUploadedIcon(saved.id, values)
    if (iconSaved) {
      emit(
        'success',
        t(props.provider ? 'settings.idp.form.updateSuccess' : 'settings.idp.form.createSuccess'),
      )
    } else {
      emit('error', t('settings.idp.form.iconSaveError'))
    }
    open.value = false
  } catch (error) {
    if (error instanceof HttpError && error.status === 412) {
      emit('error', t('settings.idp.form.staleError'))
    } else if (error instanceof HttpError && error.status === 409) {
      emit('error', t('settings.idp.form.slugConflict'))
    } else {
      emit('error', t('settings.idp.form.saveError'))
    }
  }
}

const { values, errors, isValid, isSubmitting, handleSubmit, handleBlur, reset } =
  useForm<ProviderFormValues>({
    initialValues: defaultValues(),
    validators: {
      name: compose(
        required(t('settings.idp.form.nameRequired')),
        maxLength(100, t('settings.idp.form.nameTooLong')),
      ),
      slug: compose(
        required(t('settings.idp.form.slugRequired')),
        maxLength(50, t('settings.idp.form.slugTooLong')),
        pattern(/^[a-z0-9-]+$/, t('settings.idp.form.slugInvalid')),
      ),
      issuerUrl: compose(
        required(t('settings.idp.form.issuerUrlRequired')),
        maxLength(500, t('settings.idp.form.issuerUrlTooLong')),
      ),
      clientId: compose(
        required(t('settings.idp.form.clientIdRequired')),
        maxLength(512, t('settings.idp.form.clientIdTooLong')),
      ),
      // Required only when creating; edits keep the stored secret if left blank.
      clientSecret: (value: string) =>
        props.provider
          ? null
          : compose(
              required(t('settings.idp.form.clientSecretRequired')),
              maxLength(512, t('settings.idp.form.clientSecretTooLong')),
            )(value),
      scopes: maxLength(500, t('settings.idp.form.scopesTooLong')),
    },
    onSubmit: submitForm,
  })

const isEditing = computed(() => props.provider !== null)
const selectedTemplateId = ref('')
const selectedTemplate = computed(() =>
  props.templates.find((template) => template.templateId === selectedTemplateId.value),
)
const isUploadedIcon = computed(() => values.icon === UPLOADED_ICON)
// The image to upload on save; an edit that keeps its stored image needs none.
const iconFile = ref<File | null>(null)
const iconFileError = ref<string | null>(null)
// Where the provider's stored uploaded image is served, for the picker's preview.
const storedIconSrc = computed(() =>
  props.provider?.iconUploaded
    ? resolveProviderLogo(null, {
        slug: props.provider.slug,
        iconUploaded: true,
        version: props.provider.version,
      })
    : null,
)
const iconFileMissing = computed(
  () => isUploadedIcon.value && !iconFile.value && !props.provider?.iconUploaded,
)

/**
 * Takes the picked image for upload after checking its type and size, so an
 * unusable file is refused before the form is submitted.
 *
 * @param file - The picked image, or `null` when the picker was cleared.
 */
function onIconPick(file: File | null): void {
  iconFile.value = null
  iconFileError.value = null
  if (!file) {
    return
  }
  if (!ICON_ACCEPTED_TYPES.includes(file.type)) {
    iconFileError.value = t('settings.idp.form.iconFileInvalidType')
  } else if (file.size > ICON_MAX_BYTES) {
    iconFileError.value = t('settings.idp.form.iconFileTooLarge')
  } else {
    iconFile.value = file
  }
}

/**
 * Applies a preset to the form, pre-filling identity and protocol fields. The
 * slug is derived from the name so it satisfies the backend pattern.
 *
 * @param id - The chosen template id, or `''` for none.
 */
function applyTemplate(id: string): void {
  const template = props.templates.find((entry) => entry.templateId === id)
  if (!template) {
    return
  }
  values.name = template.name
  values.slug = slugify(template.name)
  values.providerType = template.providerType
  values.issuerUrl = template.issuerUrl ?? ''
  values.scopes = template.scopes || DEFAULT_SCOPES
  values.icon = template.icon ?? ''
}

// Applying a preset pre-fills the form; choosing "custom" (empty) leaves it intact.
watch(selectedTemplateId, applyTemplate)

/** Seeds the form from the provider being edited, or pristine defaults for "add". */
function populate(): void {
  reset()
  selectedTemplateId.value = ''
  iconFile.value = null
  iconFileError.value = null
  const provider = props.provider
  if (!provider) {
    return
  }
  values.name = provider.name
  values.slug = provider.slug
  values.providerType = provider.providerType
  values.enabled = provider.enabled
  values.issuerUrl = provider.issuerUrl ?? ''
  values.clientId = provider.clientId ?? ''
  values.clientSecret = ''
  values.scopes = provider.scopes || DEFAULT_SCOPES
  values.autoCreateUsers = provider.autoCreateUsers
  values.syncUserInfo = provider.syncUserInfo
  if (provider.iconUploaded) {
    values.icon = UPLOADED_ICON
  } else if (isBuiltinProviderIcon(provider.icon)) {
    values.icon = provider.icon
  }
}

// Re-seed each time the dialog opens; the parent sets `provider` before opening.
watch(open, (isOpen) => {
  if (isOpen) {
    populate()
  }
})
</script>

<template>
  <FormDialog
    v-model:open="open"
    :title="isEditing ? t('settings.idp.form.editTitle') : t('settings.idp.form.addTitle')"
    :description="t('settings.idp.form.description')"
    :submit-label="isEditing ? t('settings.idp.form.save') : t('settings.idp.form.create')"
    :cancel-label="t('settings.idp.form.cancel')"
    :close-label="t('settings.idp.form.close')"
    :submitting="isSubmitting"
    :can-submit="isValid && !iconFileMissing && !iconFileError"
    content-class="max-w-2xl"
    @submit="handleSubmit"
  >
    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <FormField
        v-if="!isEditing"
        class="sm:col-span-2"
        :label="t('settings.idp.form.template')"
        :hint="selectedTemplate?.description"
      >
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="selectedTemplateId" :disabled="isSubmitting">
            <option value="">{{ t('settings.idp.form.templateCustom') }}</option>
            <option
              v-for="template in templates"
              :key="template.templateId"
              :value="template.templateId"
            >
              {{ template.name }}
            </option>
          </Select>
        </template>
      </FormField>

      <FormField :label="t('settings.idp.form.name')" :error="errors.name" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.name"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="name"
            maxlength="100"
            :disabled="isSubmitting"
            @blur="handleBlur('name')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('settings.idp.form.slug')"
        :error="errors.slug"
        :hint="isEditing ? undefined : t('settings.idp.form.slugHint')"
        required
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.slug"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="slug"
            maxlength="50"
            :disabled="isSubmitting || isEditing"
            @blur="handleBlur('slug')"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.idp.form.providerType')">
        <template #default="{ fieldId }">
          <Select :id="fieldId" v-model="values.providerType" :disabled="isSubmitting">
            <option value="oidc">{{ t('settings.idp.form.typeOidc') }}</option>
            <option value="oauth2">{{ t('settings.idp.form.typeOauth2') }}</option>
          </Select>
        </template>
      </FormField>

      <FormField
        class="sm:col-span-2"
        :label="t('settings.idp.form.issuerUrl')"
        :error="errors.issuerUrl"
        :hint="t('settings.idp.form.issuerUrlHint')"
        required
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.issuerUrl"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="issuerUrl"
            type="url"
            inputmode="url"
            maxlength="500"
            :disabled="isSubmitting"
            @blur="handleBlur('issuerUrl')"
          />
        </template>
      </FormField>

      <FormField :label="t('settings.idp.form.clientId')" :error="errors.clientId" required>
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.clientId"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="clientId"
            maxlength="512"
            autocomplete="off"
            :disabled="isSubmitting"
            @blur="handleBlur('clientId')"
          />
        </template>
      </FormField>

      <FormField
        :label="t('settings.idp.form.clientSecret')"
        :error="errors.clientSecret"
        :hint="isEditing ? t('settings.idp.form.clientSecretHintEdit') : undefined"
        :required="!isEditing"
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <PasswordInput
            :id="fieldId"
            v-model="values.clientSecret"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="clientSecret"
            :maxlength="512"
            autocomplete="new-password"
            :placeholder="
              isEditing ? t('settings.idp.form.clientSecretPlaceholderEdit') : undefined
            "
            :disabled="isSubmitting"
            @blur="handleBlur('clientSecret')"
          />
        </template>
      </FormField>

      <FormField
        class="sm:col-span-2"
        :label="t('settings.idp.form.scopes')"
        :error="errors.scopes"
        :hint="t('settings.idp.form.scopesHint')"
      >
        <template #default="{ fieldId, describedBy, invalid }">
          <Input
            :id="fieldId"
            v-model="values.scopes"
            :aria-describedby="describedBy"
            :aria-invalid="invalid"
            name="scopes"
            maxlength="500"
            :disabled="isSubmitting"
            @blur="handleBlur('scopes')"
          />
        </template>
      </FormField>

      <ProviderIconPicker
        v-model="values.icon"
        :file="iconFile"
        :stored-src="storedIconSrc"
        :error="iconFileError"
        :disabled="isSubmitting"
        @pick="onIconPick"
      />

      <div class="flex flex-col gap-2 sm:col-span-2">
        <Switch v-model="values.enabled" :disabled="isSubmitting">
          {{ t('settings.idp.form.enabled') }}
        </Switch>
        <Switch v-model="values.autoCreateUsers" :disabled="isSubmitting">
          {{ t('settings.idp.form.autoCreateUsers') }}
        </Switch>
        <Switch v-model="values.syncUserInfo" :disabled="isSubmitting">
          {{ t('settings.idp.form.syncUserInfo') }}
        </Switch>
      </div>

      <Alert v-if="selectedTemplate?.configurationNotes" kind="info" class="sm:col-span-2">
        {{ selectedTemplate.configurationNotes }}
      </Alert>
    </div>
  </FormDialog>
</template>
