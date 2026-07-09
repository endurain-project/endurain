import { createRouter, createWebHistory, type RouteLocationNormalized } from 'vue-router'

import type { FeatureFlags } from '@/features/config/types'
import type { User } from '@/features/auth/types'

import { useFeatureFlags } from '@/features/config/composables/useAppConfig'
import { useTelemetry } from '@/composables/useTelemetry'
import { isAdminUser } from '@/features/auth/composables/useCurrentUser'
import { useAuthStore } from '@/features/auth/stores/auth'
import { accessibleSettingsZones } from '@/features/settings/settingsNav'
import { queryClient } from '@/plugins/vueQuery'
import { queryKeys } from '@/services/queryKeys'

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    guestOnly?: boolean
    feature?: keyof FeatureFlags
    /** Render without the app chrome (navbar/footer/bottom nav), e.g. auth screens. */
    bare?: boolean
    /** Skip the shared card container; the view supplies its own surfaces. */
    cardless?: boolean
    /** Restrict the route to administrators; enforced by the global guard. */
    requiresAdmin?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  // Restore the saved position on back/forward, otherwise scroll to top so a
  // new view never opens halfway down the page.
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 }
  },
  routes: [
    {
      path: '/',
      name: 'home',
      // Route-level code splitting: each view ships as its own chunk.
      component: () => import('@/features/home/views/HomeView.vue'),
      // Cardless: the dashboard supplies its own three-column card surfaces.
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/features/auth/views/LoginView.vue'),
      meta: { requiresAuth: false, guestOnly: true, bare: true },
    },
    {
      path: '/signup',
      name: 'signup',
      component: () => import('@/features/auth/views/SignUpView.vue'),
      meta: { requiresAuth: false, guestOnly: true, feature: 'signUp', bare: true },
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('@/features/auth/views/ResetPasswordView.vue'),
      meta: { requiresAuth: false, bare: true },
    },
    {
      path: '/verify-email',
      name: 'verify-email',
      component: () => import('@/features/auth/views/EmailVerificationView.vue'),
      meta: { requiresAuth: false, bare: true },
    },
    {
      path: '/activities',
      name: 'activities',
      component: () => import('@/features/activities/views/ActivitiesView.vue'),
      // Cardless: the view supplies its own filter rail and list surfaces.
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/summary',
      name: 'summary',
      component: () => import('@/features/summary/views/SummaryView.vue'),
      // Cardless: the view supplies its own controls, totals, and table surfaces.
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/gears',
      name: 'gears',
      component: () => import('@/features/gears/views/GearsView.vue'),
      // Cardless: the view supplies its own list/card surfaces.
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/gear/:id',
      name: 'gear',
      component: () => import('@/features/gears/views/GearDetailView.vue'),
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/activity/:id',
      name: 'activity',
      component: () => import('@/features/activities/views/ActivityDetailView.vue'),
      // Auth-optional: public shareable links render for anonymous viewers,
      // gated by the activity's visibility and the public-sharing setting.
      meta: { requiresAuth: false, cardless: true },
    },
    {
      path: '/health',
      component: () => import('@/features/health/views/HealthView.vue'),
      // Cardless: the health shell supplies its own sidebar + content surfaces.
      meta: { requiresAuth: true, cardless: true },
      children: [
        {
          path: '',
          name: 'health',
          // Land on the dashboard zone by default.
          redirect: { name: 'health-dashboard' },
        },
        {
          path: 'dashboard',
          name: 'health-dashboard',
          component: () => import('@/features/health/views/HealthDashboardView.vue'),
        },
        {
          path: 'sleep',
          name: 'health-sleep',
          component: () => import('@/features/health/views/HealthSleepView.vue'),
        },
        {
          path: 'rhr',
          name: 'health-rhr',
          component: () => import('@/features/health/views/HealthRestingHeartRateView.vue'),
        },
        {
          path: 'steps',
          name: 'health-steps',
          component: () => import('@/features/health/views/HealthStepsView.vue'),
        },
        {
          path: 'weight',
          name: 'health-weight',
          component: () => import('@/features/health/views/HealthWeightView.vue'),
        },
        {
          path: 'fasting',
          name: 'health-fasting',
          component: () => import('@/features/health/views/HealthFastingView.vue'),
        },
        {
          path: 'water',
          name: 'health-water',
          component: () => import('@/features/health/views/HealthWaterView.vue'),
        },
        {
          path: 'poop',
          name: 'health-poop',
          component: () => import('@/features/health/views/HealthPoopView.vue'),
        },
      ],
    },
    {
      path: '/search',
      name: 'search',
      component: () => import('@/features/search/views/SearchView.vue'),
      // Cardless: the view supplies its own controls + results surfaces.
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/settings',
      component: () => import('@/features/settings/views/SettingsView.vue'),
      // Cardless: the settings shell supplies its own sidebar + content surfaces.
      meta: { requiresAuth: true, cardless: true },
      children: [
        {
          path: '',
          name: 'settings',
          // Land on the first zone the user can open (the profile zone for every
          // signed-in user); fall back home only if no zone is accessible.
          redirect: () => {
            const user = queryClient.getQueryData<User>(queryKeys.currentUser())
            const zones = accessibleSettingsZones(isAdminUser(user))
            return zones[0] ? { name: zones[0].name } : { name: 'home' }
          },
        },
        {
          path: 'profile',
          name: 'settings-profile',
          component: () => import('@/features/profile/views/ProfileSettingsView.vue'),
        },
        {
          path: 'goals',
          name: 'settings-goals',
          component: () => import('@/features/goals/views/GoalsSettingsView.vue'),
        },
        {
          path: 'security',
          name: 'settings-security',
          component: () => import('@/features/security/views/SecuritySettingsView.vue'),
        },
        {
          path: 'integrations',
          name: 'settings-integrations',
          component: () => import('@/features/integrations/views/IntegrationsSettingsView.vue'),
        },
        {
          path: 'import',
          name: 'settings-import',
          component: () => import('@/features/import/views/ImportSettingsView.vue'),
        },
        {
          path: 'users',
          name: 'settings-users',
          component: () => import('@/features/users/views/UsersSettingsView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'users/:id',
          name: 'settings-user-detail',
          component: () => import('@/features/users/views/UserDetailView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'identity-providers',
          name: 'settings-idp',
          component: () =>
            import('@/features/identityProviders/views/IdentityProvidersSettingsView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'server',
          name: 'settings-server',
          component: () => import('@/features/serverSettings/views/ServerSettingsView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'event-log',
          name: 'settings-event-log',
          component: () => import('@/features/eventLog/views/EventLogView.vue'),
          meta: { requiresAdmin: true },
        },
      ],
    },
    {
      path: '/user/:id',
      name: 'user',
      component: () => import('@/features/users/views/UserProfileView.vue'),
      // Cardless: the profile view supplies its own sidebar + tabbed surfaces.
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/strava/callback',
      name: 'strava-callback',
      component: () => import('@/features/integrations/views/StravaCallbackView.vue'),
      // Transient OAuth landing: finishes the link then redirects to settings.
      meta: { requiresAuth: true, bare: true },
    },
    {
      path: '/notifications',
      name: 'notifications',
      component: () => import('@/features/notifications/views/NotificationsView.vue'),
      // Cardless: the view supplies its own list surface instead of the shared card.
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/menu',
      name: 'menu',
      component: () => import('@/views/MenuMobileView.vue'),
      meta: { requiresAuth: true, cardless: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/NotFoundView.vue'),
      meta: { requiresAuth: false },
    },
  ],
})

/**
 * Global navigation guard. Restores the session on first navigation, enforces
 * feature-flag gating, and applies auth/guest-only access rules.
 *
 * @param to - The target route being navigated to.
 * @returns `true` to allow, or a redirect location to block.
 */
export async function authGuard(to: RouteLocationNormalized) {
  const auth = useAuthStore()
  const { isEnabled } = useFeatureFlags()

  if (!auth.isReady) {
    await auth.restoreSession()
  }

  if (to.meta.feature && !isEnabled(to.meta.feature)) {
    return { name: 'home' }
  }

  const requiresAuth = to.meta.requiresAuth !== false
  if (requiresAuth && !auth.isAuthenticated) {
    const query: Record<string, string> = { redirect: to.fullPath }
    // Preserve the local-login override so an operator can bypass SSO
    // auto-redirect even when landing on an auth-protected route (the flag
    // would otherwise be lost inside the encoded `redirect` param).
    if (to.query.forceLocalLogin === 'true') {
      query.forceLocalLogin = 'true'
    }
    return { name: 'login', query }
  }

  // Admin-only routes: the user is authenticated by here, so the profile is in
  // the Query cache. Deny by default when it is absent or non-admin.
  if (
    to.meta.requiresAdmin &&
    !isAdminUser(queryClient.getQueryData<User>(queryKeys.currentUser()))
  ) {
    return { name: 'home' }
  }

  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: 'home' }
  }

  return true
}

router.beforeEach(authGuard)

// Page-view analytics. The no-op telemetry adapter makes this free on
// self-hosted instances; hosted deployments register a real adapter. Only the
// route name and path are sent — never query strings, which may carry tokens.
router.afterEach((to) => {
  useTelemetry().trackEvent('page_view', { name: String(to.name ?? ''), path: to.path })
})

export default router
