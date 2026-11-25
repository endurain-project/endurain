import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { h } from 'vue'
import { Bike } from '@lucide/vue'

import { ActivityTypeBadge } from '@/components/ui/activity-type-badge'
import { Card } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { ErrorState } from '@/components/ui/error-state'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { ListPanel } from '@/components/ui/list-panel'
import { LoadingState } from '@/components/ui/loading-state'
import { MetricPill } from '@/components/ui/metric-pill'
import { Select } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'

describe('Input', () => {
  it('updates the v-model on input', async () => {
    const wrapper = mount(Input, { props: { modelValue: '' } })
    await wrapper.find('input').setValue('hello')
    const events = wrapper.emitted('update:modelValue') ?? []
    expect(events[events.length - 1]).toEqual(['hello'])
  })

  it('merges a custom class with the base styles', () => {
    const wrapper = mount(Input, { props: { class: 'pe-10' } })
    const className = wrapper.find('input').attributes('class') ?? ''
    expect(className).toContain('pe-10')
    expect(className).toContain('rounded-input')
  })
})

describe('Select', () => {
  const options = {
    default: () => [h('option', { value: 'a' }, 'A'), h('option', { value: 'b' }, 'B')],
  }

  it('updates the v-model on change', async () => {
    const wrapper = mount(Select, { props: { modelValue: 'a' }, slots: options })
    await wrapper.find('select').setValue('b')
    const events = wrapper.emitted('update:modelValue') ?? []
    expect(events[events.length - 1]).toEqual(['b'])
  })

  it('forwards attributes to the native select, not the wrapper', () => {
    const wrapper = mount(Select, {
      props: { modelValue: 'a' },
      attrs: { id: 'field-1', disabled: true, 'aria-label': 'Pick one' },
      slots: options,
    })
    const select = wrapper.find('select')
    expect(select.attributes('id')).toBe('field-1')
    expect(select.attributes('disabled')).toBeDefined()
    expect(select.attributes('aria-label')).toBe('Pick one')
    expect(wrapper.attributes('id')).toBeUndefined()
  })

  it('drops the native control chrome so it matches the button heights', () => {
    const wrapper = mount(Select, { props: { modelValue: 'a' }, slots: options })
    expect(wrapper.attributes('class')).toContain('h-9')
    const className = wrapper.find('select').attributes('class') ?? ''
    expect(className).toContain('appearance-none')
    expect(className).toContain('h-full')
    expect(wrapper.find('svg[aria-hidden="true"]').exists()).toBe(true)
  })

  it('applies a custom class to the wrapper so it can size the control', () => {
    const wrapper = mount(Select, {
      props: { modelValue: 'a', class: 'h-8 w-full' },
      slots: options,
    })
    const className = wrapper.attributes('class') ?? ''
    expect(className).toContain('h-8')
    expect(className).not.toContain('h-9')
    expect(className).toContain('w-full')
  })
})

describe('Label', () => {
  it('renders slot content and forwards the for attribute', () => {
    const wrapper = mount(Label, {
      attrs: { for: 'field-1' },
      slots: { default: 'Username' },
    })
    expect(wrapper.text()).toBe('Username')
    expect(wrapper.find('label').attributes('for')).toBe('field-1')
  })
})

describe('Card', () => {
  it('applies the padding variant', () => {
    const wrapper = mount(Card, { props: { padding: 'lg' }, slots: { default: 'Body' } })
    const className = wrapper.attributes('class') ?? ''
    expect(className).toContain('p-6')
    expect(className).toContain('rounded-card')
    expect(wrapper.text()).toBe('Body')
  })
})

describe('MetricPill', () => {
  it('renders label, value, unit, and accent colour', () => {
    const wrapper = mount(MetricPill, {
      props: { label: 'Heart rate', value: 142, unit: 'bpm', accent: 'hr' },
    })
    expect(wrapper.text()).toContain('Heart rate')
    expect(wrapper.text()).toContain('142')
    expect(wrapper.text()).toContain('bpm')
    expect(wrapper.html()).toContain('text-hr')
  })
})

describe('ActivityTypeBadge', () => {
  it('maps the activity type to its colour utilities', () => {
    const wrapper = mount(ActivityTypeBadge, {
      props: { type: 'cycling' },
      slots: { default: 'Cycling' },
    })
    const className = wrapper.find('span').attributes('class') ?? ''
    expect(className).toContain('bg-activity-cycling-bg')
    expect(className).toContain('text-activity-cycling-text')
    expect(wrapper.text()).toBe('Cycling')
  })

  it('renders a leading icon when provided', () => {
    const wrapper = mount(ActivityTypeBadge, {
      props: { type: 'running', icon: Bike },
      slots: { default: 'Running' },
    })
    expect(wrapper.find('svg').exists()).toBe(true)
    expect(wrapper.text()).toBe('Running')
  })
})

describe('EmptyState', () => {
  it('renders the rich first-time layout with action and icon slots', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'No activities yet', description: 'Import your first ride.' },
      slots: { icon: '<svg data-test="icon" />', action: '<button>Add</button>' },
    })
    expect(wrapper.attributes('data-variant')).toBe('first-time')
    expect(wrapper.text()).toContain('No activities yet')
    expect(wrapper.text()).toContain('Import your first ride.')
    expect(wrapper.find('[data-test="icon"]').exists()).toBe(true)
    expect(wrapper.find('button').text()).toBe('Add')
  })

  it('renders a quiet message for the filtered variant', () => {
    const wrapper = mount(EmptyState, {
      props: { title: 'No matches', variant: 'filtered' },
    })
    expect(wrapper.attributes('data-variant')).toBe('filtered')
    expect(wrapper.text()).toBe('No matches')
  })
})

describe('Spinner', () => {
  it('applies the requested size variant and spins', () => {
    const wrapper = mount(Spinner, { props: { size: 'lg' } })
    const className = wrapper.attributes('class') ?? ''
    expect(className).toContain('size-8')
    expect(className).toContain('animate-spin')
  })

  it('exposes a status role and label when labelled', () => {
    const wrapper = mount(Spinner, { props: { label: 'Loading' } })
    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.attributes('aria-label')).toBe('Loading')
  })

  it('is hidden from assistive tech when decorative', () => {
    const wrapper = mount(Spinner)
    expect(wrapper.attributes('aria-hidden')).toBe('true')
    expect(wrapper.attributes('role')).toBeUndefined()
  })
})

describe('Skeleton', () => {
  it('renders a pulsing placeholder merging custom classes', () => {
    const wrapper = mount(Skeleton, { props: { class: 'h-4 w-20' } })
    const className = wrapper.attributes('class') ?? ''
    expect(className).toContain('animate-pulse')
    expect(className).toContain('h-4')
    expect(wrapper.attributes('aria-hidden')).toBe('true')
  })
})

describe('LoadingState', () => {
  it('renders a labelled live region with a spinner', () => {
    const wrapper = mount(LoadingState, { props: { label: 'Loading activities' } })
    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.text()).toContain('Loading activities')
    expect(wrapper.find('[data-slot="spinner"]').exists()).toBe(true)
  })
})

describe('ErrorState', () => {
  it('renders title, description, and emits retry from the action slot', async () => {
    const wrapper = mount(ErrorState, {
      props: { title: 'Something failed', description: 'Try again later.' },
      slots: { action: '<button data-test="retry">Retry</button>' },
    })
    expect(wrapper.attributes('role')).toBe('alert')
    expect(wrapper.text()).toContain('Something failed')
    expect(wrapper.text()).toContain('Try again later.')
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(true)
  })

  it('emits a retry event when the scoped retry handler fires', async () => {
    const wrapper = mount(ErrorState, {
      props: { title: 'Failed' },
      slots: {
        action: (params: { retry: () => void }) => h('button', { onClick: params.retry }, 'Retry'),
      },
    })
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})

describe('ListPanel', () => {
  const baseProps = { errorTitle: 'Boom', retryLabel: 'Retry' }

  it('renders the loading slot while loading', () => {
    const wrapper = mount(ListPanel, {
      props: { ...baseProps, isLoading: true },
      slots: { loading: '<div data-test="loading" />', default: '<ul data-test="list" />' },
    })
    expect(wrapper.find('[data-test="loading"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="list"]').exists()).toBe(false)
  })

  it('renders the error state and emits retry', async () => {
    const wrapper = mount(ListPanel, {
      props: { ...baseProps, isError: true, errorDescription: 'desc' },
      slots: { default: '<ul data-test="list" />' },
    })
    expect(wrapper.text()).toContain('Boom')
    expect(wrapper.find('[data-test="list"]').exists()).toBe(false)
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('renders the empty slot when empty', () => {
    const wrapper = mount(ListPanel, {
      props: { ...baseProps, isEmpty: true },
      slots: { empty: '<div data-test="empty" />', default: '<ul data-test="list" />' },
    })
    expect(wrapper.find('[data-test="empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="list"]').exists()).toBe(false)
  })

  it('renders the default slot (the list) when ready', () => {
    const wrapper = mount(ListPanel, {
      props: baseProps,
      slots: { default: '<ul data-test="list" />' },
    })
    expect(wrapper.find('[data-test="list"]').exists()).toBe(true)
  })

  it('hides the header when showHeader is false', () => {
    const wrapper = mount(ListPanel, {
      props: { ...baseProps, showHeader: false },
      slots: { header: '<div data-test="header" />', default: '<ul />' },
    })
    expect(wrapper.find('[data-test="header"]').exists()).toBe(false)
  })

  it('renders the header slot by default', () => {
    const wrapper = mount(ListPanel, {
      props: baseProps,
      slots: { header: '<div data-test="header" />', default: '<ul />' },
    })
    expect(wrapper.find('[data-test="header"]').exists()).toBe(true)
  })

  it('forwards a fallthrough class onto the card root (grid layout depends on it)', () => {
    const wrapper = mount(ListPanel, {
      props: baseProps,
      attrs: { class: 'lg:col-span-4' },
      slots: { default: '<ul />' },
    })
    expect(wrapper.classes()).toContain('lg:col-span-4')
  })
})
