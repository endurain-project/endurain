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
	<div class="safe-area-container">
		<Notivue v-slot="item">
			<NotivueSwipe :item="item">
				<Notification :item="item" :theme="pastelTheme">
					<NotificationProgress :item="item" />
				</Notification>
			</NotivueSwipe>
		</Notivue>
		<div class="d-flex flex-column vh-100">
			<div class="bg-body-tertiary shadow-sm">
				<NavbarComponent class="container" />
			</div>
			<main class="container py-4 flex-grow-1">
				<RouterView />
			</main>
			<FooterComponent class="d-none d-lg-block shadow-sm"/>
			<NavbarBottomMobileComponent class="d-lg-none d-block sticky-bottom shadow-sm"/>
		</div>
	</div>
</template>

<style>
.safe-area-container {
  padding-left: env(safe-area-inset-left);
  padding-right: env(safe-area-inset-right);
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
}
</style>