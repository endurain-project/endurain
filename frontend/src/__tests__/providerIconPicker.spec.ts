import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import ProviderIconPicker from '@/features/identityProviders/components/ProviderIconPicker.vue'
import { UPLOADED_ICON } from '@/features/identityProviders/utils/providerIcon'

function mountPicker(props: Partial<InstanceType<typeof ProviderIconPicker>['$props']> = {}) {
  return mount(ProviderIconPicker, {
    props: { modelValue: '', file: null, storedSrc: null, error: null, ...props },
    global: { plugins: [i18n] },
  })
}

describe('ProviderIconPicker', () => {
  it('offers none, every built-in logo and an upload option, marking the chosen one', () => {
    const wrapper = mountPicker({ modelValue: 'keycloak' })

    const radios = wrapper.findAll('[role="radio"]')
    expect(radios).toHaveLength(7)
    const checked = radios.filter((radio) => radio.attributes('aria-checked') === 'true')
    expect(checked).toHaveLength(1)
    expect(checked[0]?.text()).toBe('Keycloak')
  })

  it('emits the chosen source', async () => {
    const wrapper = mountPicker()

    const radios = wrapper.findAll('[role="radio"]')
    const upload = radios[radios.length - 1]
    await upload?.trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([[UPLOADED_ICON]])
  })

  it('shows the upload controls only when upload is chosen', () => {
    expect(mountPicker().find('input[type="file"]').exists()).toBe(false)
    expect(mountPicker({ modelValue: UPLOADED_ICON }).find('input[type="file"]').exists()).toBe(
      true,
    )
  })

  it('previews the stored image and offers to replace it', () => {
    const wrapper = mountPicker({
      modelValue: UPLOADED_ICON,
      storedSrc: '/api/v1/public/idp/x/icon',
    })

    expect(wrapper.find('img[alt="Icon preview"]').attributes('src')).toBe(
      '/api/v1/public/idp/x/icon',
    )
    expect(wrapper.text()).toContain('Replace image')
  })

  it('previews a picked image as a data URL, which the CSP allows', async () => {
    const file = new File(['png'], 'logo.png', { type: 'image/png' })
    const wrapper = mountPicker({ modelValue: UPLOADED_ICON, file })

    await vi.waitFor(() => {
      expect(wrapper.find('img[alt="Icon preview"]').attributes('src')).toMatch(/^data:image\/png/)
    })
  })

  it('asks for an image when none is stored or picked', () => {
    const wrapper = mountPicker({ modelValue: UPLOADED_ICON })

    expect(wrapper.text()).toContain('Choose an image to upload')
  })
})
