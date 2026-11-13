import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import UnsavedChangesBar from '@/features/serverSettings/components/UnsavedChangesBar.vue'

function mountBar(canSave: boolean) {
  return mount(UnsavedChangesBar, {
    props: { saving: false, canSave },
    global: { plugins: [i18n] },
  })
}

describe('UnsavedChangesBar', () => {
  it('says why Save is disabled when the form is invalid', () => {
    const wrapper = mountBar(false)

    expect(wrapper.text()).toContain('Fix the errors above to save')
    expect(wrapper.findAll('button').slice(-1)[0]!.attributes('disabled')).toBeDefined()
  })

  it('shows no error hint when the edits can be saved', () => {
    expect(mountBar(true).text()).not.toContain('Fix the errors above to save')
  })
})
