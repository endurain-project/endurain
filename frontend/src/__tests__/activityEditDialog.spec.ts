import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ActivityEditDialog from '@/features/activities/components/ActivityEditDialog.vue'
import { makeActivity, makeActivitySummary, activityUuid, userUuid } from './fixtures/activity'
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

describe('ActivityEditDialog type', () => {
  it('does not offer the multisport type, which only the server sets', async () => {
    const wrapper = await openDialog()
    const values = wrapper.findAll('option').map((option) => option.attributes('value'))

    expect(values).toContain('run')
    expect(values).not.toContain('multisport')
  })
})

describe('ActivityEditDialog from a list row', () => {
  /** The full read of the activity: it carries the private notes and a newer version. */
  const fullDto = {
    id: activityUuid(1),
    user_id: userUuid(7),
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

describe('ActivityEditDialog on a multisport activity', () => {
  const parent = makeActivity({ activityType: 'multisport', name: 'Sunday triathlon' })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({
      id: parent.id,
      version: 2,
      name: 'Sunday triathlon',
      activity_type: 'multisport',
      distance: 1,
      is_hidden: false,
      visibility: 'public',
    })
  })

  it('shows the multisport type in a disabled select', async () => {
    const wrapper = await openDialog(parent)
    const type = wrapper.findAll('select')[0]!

    expect(type.attributes('disabled')).toBeDefined()
    expect(type.findAll('option').map((option) => option.attributes('value'))).toEqual([
      'multisport',
    ])
    expect(type.text()).toContain(i18n.global.t('activities.types.multisport'))
  })

  it('keeps the privacy editable and says it applies to every leg', async () => {
    const wrapper = await openDialog(parent)

    expect(wrapper.text()).toContain(i18n.global.t('activities.edit.multisportPrivacyNote'))
    expect(wrapper.findAll('select')[1]!.attributes('disabled')).toBeUndefined()
    const switches = wrapper.findAll('input[role="switch"]')
    expect(switches.length).toBeGreaterThan(0)
    expect(switches.every((toggle) => toggle.attributes('disabled') === undefined)).toBe(true)
  })

  it('sends the privacy fields but not the type', async () => {
    const wrapper = await openDialog(parent)

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const body = JSON.parse(vi.mocked(apiFetch).mock.calls[0]![1]!.body as string)
    expect(body).not.toHaveProperty('activity_type')
    expect(body).toMatchObject({ visibility: 'public', hide_map: false, is_hidden: false })
  })
})

describe('ActivityEditDialog on a leg', () => {
  const leg = makeActivity({ parentActivityId: activityUuid(9), activityType: 'run' })

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({
      id: leg.id,
      version: 2,
      name: 'Morning run',
      activity_type: 'run',
      distance: 1,
      is_hidden: false,
      visibility: 'public',
    })
  })

  it('disables the privacy controls with a note that privacy is set on the multisport activity', async () => {
    const wrapper = await openDialog(leg)

    expect(wrapper.text()).toContain(i18n.global.t('activities.edit.legPrivacyNote'))
    expect(wrapper.findAll('select')[1]!.attributes('disabled')).toBeDefined()
    const switches = wrapper.findAll('input[role="switch"]')
    expect(switches.length).toBeGreaterThan(0)
    expect(switches.every((toggle) => toggle.attributes('disabled') !== undefined)).toBe(true)
  })

  it('keeps the name, description, notes and type editable', async () => {
    const wrapper = await openDialog(leg)

    expect(wrapper.find('input').attributes('disabled')).toBeUndefined()
    expect(wrapper.findAll('select')[0]!.attributes('disabled')).toBeUndefined()
    expect(
      wrapper.findAll('textarea').every((area) => area.attributes('disabled') === undefined),
    ).toBe(true)
  })

  it('sends the editable fields and none of the privacy fields', async () => {
    const wrapper = await openDialog(leg)
    await wrapper.find('input').setValue('Easy run')

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const body = JSON.parse(vi.mocked(apiFetch).mock.calls[0]![1]!.body as string)
    expect(Object.keys(body).sort()).toEqual(
      ['activity_type', 'description', 'name', 'private_notes'].sort(),
    )
    expect(body).toMatchObject({ name: 'Easy run', activity_type: 'run' })
  })

  it('does not offer the multisport type for an ordinary activity either', async () => {
    const wrapper = await openDialog(leg)
    const values = wrapper.findAll('select')[0]!.findAll('option')

    expect(values.map((option) => option.attributes('value'))).not.toContain('multisport')
  })
})
