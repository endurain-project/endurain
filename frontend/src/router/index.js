import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'
import GearsView from '../views/Gears/GearsView.vue'
import GearView from '../views/Gears/GearView.vue'
import ActivityView from '../views/ActivityView.vue'
import UserView from '../views/UserView.vue'
import SettingsView from '../views/SettingsView.vue';
import NotFoundView from '../views/NotFoundView.vue';

//import { auth } from '@/services/auth';

//import { useAuthStore } from '@/stores/auth';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView
    },
    {
      path: '/gears',
      name: 'gears',
      component: GearsView
    },
    {
      path: '/gear/:id',
      name: 'gear',
      component: GearView
    },
    {
      path: '/activity/:id',
      name: 'activity',
      component: ActivityView
    },
    {
      path: '/user/:id',
      name: 'user',
      component: UserView
    },
    {
      path: '/settings',
      name: 'settings',
      component: SettingsView
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundView,
    },
  ]
})

/* router.beforeEach((to, from, next) => {
  const accessToken = localStorage.getItem('accessToken');
  const tokenType = localStorage.getItem('tokenType');

  if (!accessToken && to.path !== '/login') {
    next('/login');
  } else if (accessToken && tokenType) {
    if (auth.isTokenValid(accessToken)) {
      if (to.path === '/login') {
        next('/');
      } else {
        next();
      }
    } else {
      auth.removeLoggedUser();
      next({ path: '/login', query: { sessionExpired: 'true' } });
    }
  } else {
    next();
  }
}); */

export default router;