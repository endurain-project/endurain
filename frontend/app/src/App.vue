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

<style>
:root {
  /* Your variables */
  --header-height: 65px;
  --container-padding: 0px;
  --container-width: 1300px;

  /* Set the maximum width of the stream */
  --nv-root-width: var(--container-width);

  /* Add the top padding and place it below the header */
  --nv-root-top: calc(var(--header-height) + var(--container-padding));

  /* Add the same left-right paddings of your app container */
  --nv-root-left: var(--container-padding);
  --nv-root-right: var(--container-padding);
}
</style>