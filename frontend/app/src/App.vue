<script setup>
import { RouterView } from "vue-router";
import NavbarComponent from "./components/Navbar/NavbarComponent.vue";
import NavbarBottomMobileComponent from "./components/Navbar/NavbarBottomMobileComponent.vue";
import FooterComponent from "./components/FooterComponent.vue";
import {
	Notivue,
	Notification,
	NotivueSwipe,
	NotificationProgress,
	pastelTheme,
} from "notivue";
</script>

<template>
	<Notivue v-slot="item">
		<NotivueSwipe :item="item">
			<Notification :item="item" :theme="pastelTheme">
				<NotificationProgress :item="item" />
			</Notification>
		</NotivueSwipe>
	</Notivue>
	<div class="d-flex flex-column min-vh-100 safe-area">
		<!-- Top Navbar with safe-area padding -->
		<div class="bg-body-tertiary shadow-sm">
			<NavbarComponent class="container"/>
		</div>

		<!-- Main content -->
		<main class="container py-4 flex-grow-1">
			<RouterView />
		</main>

		<!-- Desktop Footer -->
		<FooterComponent class="d-none d-lg-block shadow-sm"/>

		<!-- Bottom Mobile Navbar with safe-area padding -->
		<NavbarBottomMobileComponent 
			class="d-lg-none d-block sticky-bottom shadow-sm"
		/>
	</div>
</template>

<style>
	/* iOS PWA Safe‐Area Insets */
	.safe-area {
		padding:
			env(safe-area-inset-top)
			env(safe-area-inset-right)
			env(safe-area-inset-bottom)
			env(safe-area-inset-left);
	}

	/* Fallback for older iOS (Safari < 11) */
	@supports not (padding: env(safe-area-inset-top)) {
		.safe-area {
			padding:
			constant(safe-area-inset-top)
			constant(safe-area-inset-right)
			constant(safe-area-inset-bottom)
			constant(safe-area-inset-left);
		}
	}
</style>