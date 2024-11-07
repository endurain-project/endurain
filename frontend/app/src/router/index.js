import { createRouter, createWebHistory } from 'vue-router'

//import { auth } from '@/services/auth';

import { useAuthStore } from '@/stores/authStore';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('../views/HomeView.vue')
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue')
    },
    {
      path: '/gears',
      name: 'gears',
      component: () => import('../views/Gears/GearsView.vue')
    },
    {
      path: '/gear/:id',
      name: 'gear',
      component: () => import('../views/Gears/GearView.vue')
    },
    {
      path: '/activity/:id',
      name: 'activity',
      component: () => import('../views/ActivityView.vue')
    },
    {
      path: '/health',
      name: 'health',
      component: () => import('../views/HealthView.vue')
    },
    {
      path: '/user/:id',
      name: 'user',
      component: () => import('../views/UserView.vue')
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue')
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('../views/NotFoundView.vue'),
    },
  ]
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore();

  if (!authStore.isAuthenticated && to.path !== '/login') {
    next('/login');
   } else if (authStore.isAuthenticated ) {
    //if (auth.isTokenValid(accessToken)) {
      if (to.path === '/login') {
        next('/');
      } else {
        next();
      }
    //} else {
    //  auth.removeLoggedUser();
    //  next({ path: '/login', query: { sessionExpired: 'true' } });
    //}
  } else {
    next();
  }
});

export default router;