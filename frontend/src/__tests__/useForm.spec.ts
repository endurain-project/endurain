import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { h, nextTick } from 'vue'

import { FormField } from '@/components/ui/form-field'
import { useForm } from '@/composables/useForm'
import { compose, email, maxLength, minLength, pattern, required } from '@/utils/validators'

describe('validators', () => {
  it('required rejects empty-ish values and accepts content', () => {
    const validate = required<unknown>('Required')
    expect(validate(null)).toBe('Required')
    expect(validate(undefined)).toBe('Required')
    expect(validate('')).toBe('Required')
    expect(validate('   ')).toBe('Required')
    expect(validate([])).toBe('Required')
    expect(validate('value')).toBeNull()
    expect(validate(['x'])).toBeNull()
    expect(validate(0)).toBeNull()
    expect(validate(false)).toBeNull()
  })

  it('minLength and maxLength measure trimmed length', () => {
    expect(minLength(3, 'Too short')('ab')).toBe('Too short')
    expect(minLength(3, 'Too short')('  ab  ')).toBe('Too short')
    expect(minLength(3, 'Too short')('abc')).toBeNull()
    expect(maxLength(3, 'Too long')('abcd')).toBe('Too long')
    expect(maxLength(3, 'Too long')('abc')).toBeNull()
  })

  it('email accepts valid addresses and lets empty pass', () => {
    expect(email('Bad email')('')).toBeNull()
    expect(email('Bad email')('user@example.com')).toBeNull()
    expect(email('Bad email')('not-an-email')).toBe('Bad email')
  })

  it('pattern enforces the regex but lets empty pass', () => {
    const digits = pattern(/^\d+$/, 'Digits only')
    expect(digits('')).toBeNull()
    expect(digits('123')).toBeNull()
    expect(digits('12a')).toBe('Digits only')
  })

  it('compose returns the first failure in order', () => {
    const validate = compose(required<string>('Required'), minLength(3, 'Too short'))
    expect(validate('')).toBe('Required')
    expect(validate('ab')).toBe('Too short')
    expect(validate('abc')).toBeNull()
  })
})

interface LoginValues {
  email: string
  password: string
}

function createLoginForm(onSubmit = vi.fn<(values: LoginValues) => void | Promise<void>>()) {
  return useForm<LoginValues>({
    initialValues: { email: '', password: '' },
    validators: {
      email: compose(required('Email is required'), email('Enter a valid email')),
      password: required('Password is required'),
    },
    onSubmit,
  })
}

describe('useForm', () => {
  it('reports invalid while required fields are empty', () => {
    const form = createLoginForm()
    expect(form.isValid.value).toBe(false)
    expect(form.isDirty.value).toBe(false)
  })

  it('validateField records and clears a field error', () => {
    const form = createLoginForm()

    expect(form.validateField('email')).toBe('Email is required')
    expect(form.errors.value.email).toBe('Email is required')

    form.values.email = 'user@example.com'
    expect(form.validateField('email')).toBeNull()
    expect(form.errors.value.email).toBeUndefined()
  })

  it('handleBlur marks the field touched and validates it', () => {
    const form = createLoginForm()
    form.handleBlur('password')
    expect(form.touched.value.password).toBe(true)
    expect(form.errors.value.password).toBe('Password is required')
  })

  it('setFieldValue re-validates only after the field is touched', () => {
    const form = createLoginForm()

    form.setFieldValue('email', 'bad')
    expect(form.errors.value.email).toBeUndefined()

    form.handleBlur('email')
    expect(form.errors.value.email).toBe('Enter a valid email')

    form.setFieldValue('email', 'user@example.com')
    expect(form.errors.value.email).toBeUndefined()
  })

  it('tracks dirtiness against the initial values', () => {
    const form = createLoginForm()
    expect(form.isDirty.value).toBe(false)
    form.values.email = 'user@example.com'
    expect(form.isDirty.value).toBe(true)
  })

  it('measures dirtiness from the last markPristine() baseline', () => {
    const form = createLoginForm()
    form.values.email = 'user@example.com'
    form.markPristine()
    expect(form.isDirty.value).toBe(false)
    form.values.email = 'other@example.com'
    expect(form.isDirty.value).toBe(true)
    form.reset()
    expect(form.isDirty.value).toBe(false)
  })

  it('merges server-side errors', () => {
    const form = createLoginForm()
    form.setErrors({ email: 'Already registered' })
    expect(form.errors.value.email).toBe('Already registered')
  })

  it('blocks submit and marks fields touched when invalid', async () => {
    const onSubmit = vi.fn<(values: LoginValues) => void>()
    const form = createLoginForm(onSubmit)

    await form.handleSubmit()

    expect(onSubmit).not.toHaveBeenCalled()
    expect(form.touched.value.email).toBe(true)
    expect(form.touched.value.password).toBe(true)
    expect(form.errors.value.email).toBe('Email is required')
  })

  it('submits the current values when valid', async () => {
    const onSubmit = vi.fn<(values: LoginValues) => void>()
    const form = createLoginForm(onSubmit)

    form.values.email = 'user@example.com'
    form.values.password = 'secret'
    await form.handleSubmit()

    expect(onSubmit).toHaveBeenCalledWith({ email: 'user@example.com', password: 'secret' })
    expect(form.isSubmitting.value).toBe(false)
    expect(form.submitError.value).toBeNull()
  })

  it('captures a thrown submit error instead of rethrowing', async () => {
    const onSubmit = vi
      .fn<(values: LoginValues) => Promise<void>>()
      .mockRejectedValue(new Error('Network down'))
    const form = createLoginForm(onSubmit)

    form.values.email = 'user@example.com'
    form.values.password = 'secret'
    await form.handleSubmit()

    expect(form.submitError.value).toBe('Network down')
    expect(form.isSubmitting.value).toBe(false)
  })

  it('reset restores initial values and clears state', () => {
    const form = createLoginForm()
    form.values.email = 'user@example.com'
    form.handleBlur('password')

    form.reset()

    expect(form.values.email).toBe('')
    expect(form.errors.value.password).toBeUndefined()
    expect(form.touched.value.password).toBeUndefined()
    expect(form.isDirty.value).toBe(false)
  })
})

describe('FormField', () => {
  it('associates the label, control, and error via ids', async () => {
    const wrapper = mount(FormField, {
      props: { label: 'Email', required: true, error: 'Email is required' },
      slots: {
        default: ({ fieldId, describedBy, invalid }) =>
          h('input', { id: fieldId, 'aria-describedby': describedBy, 'aria-invalid': invalid }),
      },
    })
    await nextTick()

    const input = wrapper.find('input')
    const label = wrapper.find('label')
    const error = wrapper.find('[role="alert"]')

    expect(label.attributes('for')).toBe(input.attributes('id'))
    expect(error.text()).toBe('Email is required')
    expect(input.attributes('aria-describedby')).toBe(error.attributes('id'))
    expect(input.attributes('aria-invalid')).toBe('true')
    expect(wrapper.text()).toContain('*')
  })

  it('shows the hint when there is no error', () => {
    const wrapper = mount(FormField, {
      props: { label: 'Email', hint: 'We never share it' },
      slots: { default: ({ fieldId }) => h('input', { id: fieldId }) },
    })

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.text-hint').text()).toBe('We never share it')
  })
})
