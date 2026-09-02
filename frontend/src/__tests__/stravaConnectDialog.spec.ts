import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import StravaConnectDialog from '@/features/integrations/components/StravaConnectDialog.vue'

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form
 * renders inline where the test can drive it. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog() {
  return mount(StravaConnectDialog, {
    props: { open: true, pending: false },
    global: {
      plugins: [i18n],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
      },
    },
  })
}

describe('StravaConnectDialog submit', () => {
  it('emits the client credentials when both fields hold a value', async () => {
    // Regression: `<input type="number">` + `v-model` yields a `number`, which
    // previously crashed the `canSubmit` computed (`clientId.value.trim()`) on
    // the first keystroke and tore the dialog down.
    const wrapper = mountDialog()

    await wrapper.find('#strava-client-id').setValue('12345')
    await wrapper.find('#strava-client-secret').setValue('s3cret')

    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('submit')).toEqual([[{ clientId: 12345, clientSecret: 's3cret' }]])
  })

  it('does not emit while the client id is blank', async () => {
    const wrapper = mountDialog()

    await wrapper.find('#strava-client-secret').setValue('s3cret')
    await wrapper.find('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
  })
})
