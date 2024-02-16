import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import LoginView from '../views/LoginView.vue'

import { auth } from '@/services/auth';

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
    }
  ]
})

router.beforeEach((to, from, next) => {
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
});

export default router;