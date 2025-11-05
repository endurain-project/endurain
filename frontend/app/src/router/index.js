import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

// Lazy load all routes
const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/signup',
    name: 'signup',
    component: () => import('../views/SignUpView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/verify-email',
    name: 'verify-email',
    component: () => import('../views/EmailVerificationView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/reset-password',
    name: 'reset-password',
    component: () => import('../views/ResetPasswordView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/gears',
    name: 'gears',
    component: () => import('../views/Gears/GearsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/gear/:id',
    name: 'gear',
    component: () => import('../views/Gears/GearView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/activity/:id',
    name: 'activity',
    component: () => import('../views/ActivityView.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/activities',
    name: 'activities',
    component: () => import('../views/ActivitiesView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/summary',
    name: 'summary',
    component: () => import('../views/SummaryView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/health',
    name: 'health',
    component: () => import('../views/HealthView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/user/:id',
    name: 'user',
    component: () => import('../views/UserView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('../views/SearchView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/menu',
    name: 'menu',
    component: () => import('../views/MenuMobileView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('../views/NotificationsView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/strava/callback',
    name: 'strava-callback',
    component: () => import('../views/Strava/StravaCallbackView.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFoundView.vue'),
    meta: { requiresAuth: false }
  }
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior(to, from, savedPosition) {
    // Return to saved position or scroll to top
    return savedPosition || { top: 0 }
  }
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()
  const requiresAuth = to.meta.requiresAuth !== false

  if (requiresAuth && !authStore.isAuthenticated) {
    next({
      name: 'login', query: {
        redirect: to.path,
        ...to.query
      }
    })
  } else if (to.name === 'login' && authStore.isAuthenticated) {
    next({ name: 'home' })
  } else {
    next()
  }
})

export default router
