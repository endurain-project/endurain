<script setup>
import { RouterView } from "vue-router";
import NavbarComponent from "./components/Navbar/NavbarComponent.vue";
import NavbarBottomMobileComponent from "./components/Navbar/NavbarBottomMobileComponent.vue";
import FooterComponent from "./components/FooterComponent.vue";
import {
	Notivue,
	Notification,
	NotificationProgress,
	pastelTheme,
} from "notivue";
</script>

<template>
	<Notivue v-slot="item">
		<Notification :item="item" :theme="pastelTheme">
			<NotificationProgress :item="item" />
		</Notification>
	</Notivue>
	<div class="d-flex flex-column vh-100">
		<div class="bg-body-tertiary">
			<NavbarComponent class="container" />
		</div>
		<main class="container py-4 flex-grow-1">
			<RouterView />
		</main>
		<FooterComponent class="d-none d-sm-block"/>
		<NavbarBottomMobileComponent class="d-lg-none d-block fixed-bottom"/>
	</div>
</template>