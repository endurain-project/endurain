import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/authStore";

const router = createRouter({
	history: createWebHistory(import.meta.env.BASE_URL),
	routes: [
		{
			path: "/",
			name: "home",
			component: () => import("../views/HomeView.vue"),
		},
		{
			path: "/login",
			name: "login",
			component: () => import("../views/LoginView.vue"),
		},
		{
			path: "/gears",
			name: "gears",
			component: () => import("../views/Gears/GearsView.vue"),
		},
		{
			path: "/gear/:id",
			name: "gear",
			component: () => import("../views/Gears/GearView.vue"),
		},
		{
			path: "/activity/:id",
			name: "activity",
			component: () => import("../views/ActivityView.vue"),
		},
		{
			path: '/activities',
			name: 'activities',
			component: () => import('../views/ActivitiesView.vue'),
		},
		{
			path: '/summary',
			name: 'summary',
			component: () => import('../views/SummaryView.vue'),
		},
		{
			path: "/health",
			name: "health",
			component: () => import("../views/HealthView.vue"),
		},
		{
			path: "/user/:id",
			name: "user",
			component: () => import("../views/UserView.vue"),
		},
		{
			path: "/search",
			name: "search",
			component: () => import("../views/SearchView.vue"),
		},
		{
			path: "/settings",
			name: "settings",
			component: () => import("../views/SettingsView.vue"),
		},
		{
			path: "/menu",
			name: "menu",
			component: () => import("../views/MenuMobileView.vue"),
		},
		{
			path: "/strava/callback",
			name: "strava-callback",
			component: () => import("../views/Strava/StravaCallbackView.vue"),
		},
		{
			path: "/:pathMatch(.*)*",
			name: "not-found",
			component: () => import("../views/NotFoundView.vue"),
		},
	],
});

router.beforeEach((to, from, next) => {
	const authStore = useAuthStore();

	if (!authStore.isAuthenticated && to.path !== "/login" && !to.path.startsWith("/activity/")) {
		next("/login");
	} else if (authStore.isAuthenticated) {
		if (to.path === "/login") {
			next("/");
		} else {
			next();
		}
	} else {
		next();
	}
});

export default router;
