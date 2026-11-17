import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import i18n from '@/i18n'
import PasswordStrengthMeter from '@/features/security/components/PasswordStrengthMeter.vue'

const { check, loaded } = vi.hoisted(() => ({
  check: vi.fn<(password: string, userInputs?: (string | number)[]) => { score: number }>(),
  loaded: { core: 0, common: 0, en: 0 },
}))

vi.mock('@zxcvbn-ts/core', () => {
  loaded.core += 1
  return {
    ZxcvbnFactory: class {
      check = check
    },
  }
})
vi.mock('@zxcvbn-ts/language-common', () => {
  loaded.common += 1
  return { dictionary: {}, adjacencyGraphs: {} }
})
vi.mock('@zxcvbn-ts/language-en', () => {
  loaded.en += 1
  return { dictionary: {}, translations: {} }
})

// The scorer is imported once per module graph, so the laziness checks run first.
describe('PasswordStrengthMeter', () => {
  beforeEach(() => {
    check.mockReset()
    check.mockReturnValue({ score: 0 })
  })

  it('is hidden while the password is empty and does not load the scorer', async () => {
    const wrapper = mount(PasswordStrengthMeter, {
      props: { password: '' },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(wrapper.find('[data-strength-bar]').exists()).toBe(false)
    expect(wrapper.text()).toBe('')
    expect(loaded).toEqual({ core: 0, common: 0, en: 0 })
    expect(check).not.toHaveBeenCalled()
  })

  it('imports zxcvbn and its dictionaries only once a password is typed', async () => {
    const wrapper = mount(PasswordStrengthMeter, {
      props: { password: '' },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    expect(loaded).toEqual({ core: 0, common: 0, en: 0 })

    await wrapper.setProps({ password: 'a' })

    await vi.waitFor(() => expect(loaded).toEqual({ core: 1, common: 1, en: 1 }))
  })

  it.each([
    [0, 'Too weak', 1],
    [1, 'Weak', 1],
    [2, 'Fair', 2],
    [3, 'Good', 3],
    [4, 'Strong', 4],
  ])('shows score %i as "%s" with %i filled segments', async (score, label, filled) => {
    check.mockReturnValue({ score })
    const wrapper = mount(PasswordStrengthMeter, {
      props: { password: 'hunter2' },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain(label)
    expect(wrapper.findAll('[data-strength-segment]')).toHaveLength(4)
    expect(wrapper.findAll('[data-strength-segment="filled"]')).toHaveLength(filled)
  })

  it('announces the label politely and never shows zxcvbn feedback text', async () => {
    check.mockReturnValue({ score: 2, feedback: { warning: 'This is a top-10 password' } } as never)
    const wrapper = mount(PasswordStrengthMeter, {
      props: { password: 'hunter2' },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(wrapper.get('[aria-live="polite"]').text()).toContain('Fair')
    expect(wrapper.text()).not.toContain('top-10')
  })

  it('scores with the account details as user inputs and rescoring follows the password', async () => {
    const wrapper = mount(PasswordStrengthMeter, {
      props: {
        password: 'adalovelace1',
        userInputs: ['ada', 'ada@example.com', '', 'Ada Lovelace'],
      },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(check).toHaveBeenLastCalledWith('adalovelace1', [
      'ada',
      'ada@example.com',
      'Ada Lovelace',
    ])

    check.mockReturnValue({ score: 4 })
    await wrapper.setProps({ password: 'adalovelace1-longer' })
    await flushPromises()

    expect(check).toHaveBeenLastCalledWith('adalovelace1-longer', [
      'ada',
      'ada@example.com',
      'Ada Lovelace',
    ])
    expect(wrapper.text()).toContain('Strong')
  })

  it('hides again when the field is cleared', async () => {
    const wrapper = mount(PasswordStrengthMeter, {
      props: { password: 'abc' },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    expect(wrapper.find('[data-strength-bar]').exists()).toBe(true)

    await wrapper.setProps({ password: '' })
    await flushPromises()

    expect(wrapper.find('[data-strength-bar]').exists()).toBe(false)
  })
})
