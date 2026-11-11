import type { StepUpAction } from '@/features/security/types'

/** The tabs of the security page, in display order. */
export const SECURITY_TABS = ['account', 'sessions', 'danger'] as const

/** One tab of the security page. */
export type SecurityTab = (typeof SECURITY_TABS)[number]

/** The tab shown when the URL names none, or an unknown one. */
export const DEFAULT_SECURITY_TAB: SecurityTab = 'account'

const ACTION_TABS: Partial<Record<StepUpAction, SecurityTab>> = {
  email_change: 'account',
  username_change: 'account',
  idp_link: 'account',
  idp_unlink: 'account',
  mfa_enable: 'account',
  mfa_disable: 'account',
  mfa_backup_codes: 'account',
  profile_device_forget: 'sessions',
  profile_devices_forget_others: 'sessions',
  api_key_create: 'sessions',
  account_delete: 'danger',
}

/**
 * The tab whose card started a step-up. The identity-provider callback returns to the page without its
 * `?tab=`, so the page opens this tab to show the card that reopens its dialog.
 *
 * @param action - The operation the step-up authorised.
 * @returns The tab that holds the card, or the default tab for an action the page does not own.
 */
export function securityTabForAction(action: StepUpAction): SecurityTab {
  return ACTION_TABS[action] ?? DEFAULT_SECURITY_TAB
}
