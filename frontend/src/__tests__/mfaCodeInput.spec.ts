import { describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import i18n from '@/i18n'
import MfaCodeInput from '@/features/auth/components/MfaCodeInput.vue'
import { isMfaCodeComplete } from '@/features/auth/utils/mfaCode'

/**
 * Mounts the field in a form whose submit button is enabled only when `ready` holds.
 *
 * @param ready - Whether the form's submit button is enabled.
 * @returns The wrapper, the bound code and the submit spy.
 */
function mountInForm(ready = true) {
  const code = ref('')
  const onSubmit = vi.fn<() => void>()
  const Host = defineComponent({
    components: { MfaCodeInput },
    setup: () => ({ code, onSubmit, ready }),
    template: `
      <form @submit.prevent="onSubmit">
        <MfaCodeInput id="code" v-model="code" />
        <button type="submit" :disabled="!ready">Verify</button>
      </form>
    `,
  })
  const wrapper = mount(Host, { global: { plugins: [i18n] }, attachTo: document.body })
  return { wrapper, code, onSubmit }
}

const boxes = (wrapper: ReturnType<typeof mount>) => wrapper.findAll('[data-slot="mfa-code-box"]')
const toggle = (wrapper: ReturnType<typeof mount>) => wrapper.find('button[type="button"]')

describe('isMfaCodeComplete', () => {
  it.each(['123456', '022 643', 'A3K97BDF', 'a3k9-7bdf'])('accepts %j', (code) => {
    expect(isMfaCodeComplete(code)).toBe(true)
  })

  it.each(['', '12345', '1234567', 'A3K97BD', 'A3K9-7BDF9'])('refuses %j', (code) => {
    expect(isMfaCodeComplete(code)).toBe(false)
  })
})

describe('MfaCodeInput', () => {
  it('takes six digits in authenticator mode and drops anything else', async () => {
    const { wrapper, code } = mountInForm()
    const input = wrapper.get('#code')

    expect(boxes(wrapper)).toHaveLength(6)
    expect(input.attributes('inputmode')).toBe('numeric')
    await input.setValue('1a2-b3')

    expect(code.value).toBe('123')
    expect((input.element as HTMLInputElement).value).toBe('123')
    expect(boxes(wrapper).map((box) => box.text())).toEqual(['1', '2', '3', '', '', ''])
    wrapper.unmount()
  })

  it('switches to eight upper-case letters and digits for a backup code, clearing the code', async () => {
    const { wrapper, code } = mountInForm()
    await wrapper.get('#code').setValue('12')

    await toggle(wrapper).trigger('click')

    expect(code.value).toBe('')
    expect(boxes(wrapper)).toHaveLength(8)
    expect(wrapper.get('#code').attributes('inputmode')).toBe('text')
    expect(toggle(wrapper).text()).toBe(i18n.global.t('login.mfaCodeInput.useAuthenticator'))
    await wrapper.get('#code').setValue('a3k9-7b')
    expect(code.value).toBe('A3K97B')

    await toggle(wrapper).trigger('click')
    expect(boxes(wrapper)).toHaveLength(6)
    expect(code.value).toBe('')
    wrapper.unmount()
  })

  it('switches to backup-code mode when a backup code is pasted', async () => {
    const { wrapper, code } = mountInForm()

    await wrapper.get('#code').setValue('a3k9-7bdf')

    expect(code.value).toBe('A3K97BDF')
    expect(boxes(wrapper)).toHaveLength(8)
    wrapper.unmount()
  })

  it('submits the form once the code is whole', async () => {
    const { wrapper, onSubmit } = mountInForm()

    await wrapper.get('#code').setValue('12345')
    await flushPromises()
    expect(onSubmit).not.toHaveBeenCalled()

    await wrapper.get('#code').setValue('123456')
    await flushPromises()
    expect(onSubmit).toHaveBeenCalledTimes(1)

    // A seventh digit is dropped and leaves the code unchanged, so nothing is sent again.
    await wrapper.get('#code').setValue('1234567')
    await flushPromises()
    expect(onSubmit).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('does not submit while the form is not ready', async () => {
    const { wrapper, onSubmit } = mountInForm(false)

    await wrapper.get('#code').setValue('123456')
    await flushPromises()

    expect(onSubmit).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
