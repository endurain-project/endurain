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
	<UseScreenSafeArea top right bottom left>
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
	</UseScreenSafeArea>
</template>
