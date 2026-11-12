import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ActivityEditDialog from '@/features/activities/components/ActivityEditDialog.vue'
import { makeActivity, makeActivitySummary, activityUuid } from './fixtures/activity'
import type { Activity, ActivitySummary } from '@/features/activities/types'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
  HttpError: class extends Error {},
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog(activity: Activity | ActivitySummary = makeActivity()) {
  const wrapper = mount(ActivityEditDialog, {
    props: { open: false, activity },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
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
  await wrapper.setProps({ open: true })
  return wrapper
}

describe('ActivityEditDialog name', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a required-name error for a blank name and sends no request', async () => {
    const wrapper = await openDialog()
    const name = wrapper.find('input')

    await name.setValue('   ')
    await name.trigger('blur')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('activities.edit.nameRequired'))
    expect(apiFetch).not.toHaveBeenCalled()
  })
})

describe('ActivityEditDialog from a list row', () => {
  /** The full read of the activity: it carries the private notes and a newer version. */
  const fullDto = {
    id: activityUuid(1),
    user_id: 7,
    version: 6,
    name: 'Morning run',
    activity_type: 'run',
    distance: 10000,
    is_hidden: false,
    visibility: 'public',
    private_notes: 'Left knee felt tight',
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a loading state, reads the full activity, then fills the form from it', async () => {
    let resolve: (value: unknown) => void = () => undefined
    vi.mocked(apiFetch).mockReturnValue(new Promise((done) => (resolve = done)))

    const wrapper = await openDialog(makeActivitySummary({ id: activityUuid(1) }))

    expect(apiFetch).toHaveBeenCalledWith(`/activities/${activityUuid(1)}`)
    expect(wrapper.text()).toContain(i18n.global.t('activities.edit.loading'))
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeDefined()

    resolve(fullDto)
    await flushPromises()

    expect(wrapper.text()).not.toContain(i18n.global.t('activities.edit.loading'))
    const notes = wrapper
      .findAll('textarea')
      .map((area) => (area.element as HTMLTextAreaElement).value)
    expect(notes).toContain('Left knee felt tight')
  })

  it('saves with the version of the full activity as If-Match', async () => {
    vi.mocked(apiFetch).mockResolvedValue(fullDto)
    const wrapper = await openDialog(makeActivitySummary({ id: activityUuid(1), version: 2 }))
    await flushPromises()

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiFetch).toHaveBeenCalledWith(
      `/activities/${activityUuid(1)}`,
      expect.objectContaining({ method: 'PATCH', headers: { 'If-Match': '"6"' } }),
    )
  })

  it('offers a retry when the activity cannot be read', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('boom'))
    const wrapper = await openDialog(makeActivitySummary({ id: activityUuid(1) }))
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('activities.edit.loadError'))
    expect(wrapper.find('input').exists()).toBe(false)
  })

  it('reads nothing when it is given the full activity', async () => {
    const wrapper = await openDialog(makeActivity({ privateNotes: 'Already here' }))
    await flushPromises()

    expect(apiFetch).not.toHaveBeenCalled()
    const notes = wrapper
      .findAll('textarea')
      .map((area) => (area.element as HTMLTextAreaElement).value)
    expect(notes).toContain('Already here')
  })
})
