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
import { useScreenSafeArea } from '@vueuse/core'

const {
  top,
  right,
  bottom,
  left,
} = useScreenSafeArea()
</script>

<template>
	{{ top }} {{ right }} {{ bottom }} {{ left }}
	top: {{ top }}px
	<Notivue v-slot="item">
		<NotivueSwipe :item="item">
			<Notification :item="item" :theme="pastelTheme">
				<NotificationProgress :item="item" />
			</Notification>
		</NotivueSwipe>
	</Notivue>
	<div class="d-flex flex-column vh-100">
		<!-- Top Navbar with safe-area padding -->
		<div class="bg-body-tertiary shadow-sm" :style="{ paddingTop: `${top}px` }">
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
			:style="{ paddingBottom: `${bottom}px` }"
		/>
	</div>
</template>
