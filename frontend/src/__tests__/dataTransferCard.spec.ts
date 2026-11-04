import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { ProfileImportStatus } from '@/features/profile/types'

import i18n from '@/i18n'
import DataTransferCard from '@/features/profile/components/DataTransferCard.vue'

const importStatus = ref<ProfileImportStatus | null>(null)

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: vi.fn<() => void>() }),
}))
vi.mock('@/features/profile/composables/useDataTransfer', () => ({
  useExportProfileMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useDownloadProfileExportMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useImportProfileMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useProfileExportQuery: () => ({ data: computed(() => null) }),
  useProfileImportQuery: () => ({ data: computed(() => importStatus.value) }),
}))

const mounted: Array<{ unmount: () => void }> = []

afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
})

describe('DataTransferCard', () => {
  it('explains that an archive from a different account was refused', () => {
    // The generated ImportFailure union predates `wrong_account`, so the status is cast.
    importStatus.value = {
      status: 'failed',
      failure: 'wrong_account',
      imported: null,
    } as unknown as ProfileImportStatus
    const wrapper = mount(DataTransferCard, { props: { userId: 1 }, global: { plugins: [i18n] } })
    mounted.push(wrapper)

    expect(wrapper.get('[role="status"]').text()).toBe(
      "The import didn't complete: the archive was exported from a different account. Nothing was imported.",
    )
  })
})
