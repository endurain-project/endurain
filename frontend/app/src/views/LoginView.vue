<template>
  <div class="form-signin w-100 m-auto text-center p-5" style="max-width: 500px">
    <form @submit.prevent="submitForm">
        <h1>Endurain</h1>
        <p>{{ $t("loginView.subtitle") }}</p>
        <br>

        <div class="form-floating">
            <input type="text" class="form-control" id="floatingInput" name="loginUsername" :placeholder='$t("loginView.username")' v-model="username" required>
            <label for="loginUsername">{{ $t("loginView.username") }}</label>
        </div>
        <br>
        <div class="form-floating">
            <input type="password" class="form-control" name="loginPassword" :placeholder='$t("loginView.password")' v-model="password" required>
            <label for="loginPassword">{{ $t("loginView.password") }}</label>
        </div>
        <br>
        <button class="w-100 btn btn-lg btn-primary" type="submit">{{ $t("loginView.signInButton") }}</button>
        <!--<div>
            <br>
            <p>{{ $t("loginView.signUpText") }}</p>
            <button class="w-100 btn btn-lg btn-primary disabled" type="submit">{{ $t("loginView.signUpButton") }}></button>
        </div>-->
    </form>
  </div>
</template>

<script>
// Importing the vue composition API
import { ref, onMounted } from "vue";
// Importing the router
import { useRoute, useRouter } from "vue-router";
// Importing the i18n
import { useI18n } from "vue-i18n";
// Import Notivue push
import { push } from "notivue";
// Importing the stores
import { useAuthStore } from "@/stores/authStore";
// Importing the services for the login
import { session } from "@/services/sessionService";
import { profile } from "@/services/profileService";

// Exporting the default object
export default {
	// Setup function
	setup() {
		// Variables
		const route = useRoute();
		const router = useRouter();
		const { locale, t } = useI18n();
		const username = ref("");
		const password = ref("");
		const authStore = useAuthStore();

		// Handle the form submission
		const submitForm = async () => {
			// Create the form data
			const formData = new URLSearchParams();
			formData.append("grant_type", "password");
			formData.append("username", username.value);
			formData.append("password", password.value);

			try {
				// Get the token
				const session_id = await session.authenticateUser(formData);

				// Get logged user information
				const userProfile = await profile.getProfileInfo();

				// Store the user in the auth store
				authStore.setUser(userProfile, session_id, locale);

				// Redirect to the home page
				return router.push("/");
			} catch (error) {
				// Handle the error
				if (error.toString().includes("401")) {
					push.error(`${t("loginView.error401")} - ${error}`);
				} else if (error.toString().includes("403")) {
					push.error(`${t("loginView.error403")} - ${error}`);
				} else if (error.toString().includes("500")) {
					push.error(`${t("loginView.error500")} - ${error}`);
				} else {
					push.error(`${t("loginView.errorUndefined")} - ${error}`);
				}
			}
		};

		onMounted(() => {
			// Check if the session expired
			if (route.query.sessionExpired === "true") {
				push.warning(t("loginView.sessionExpired"));
			}
			// Check if the public activity was not found
			if (route.query.errorPublicActivityNotFound === "true") {
				push.error(t("loginView.errorPublicActivityNotFound"));
			}
			// Check if the public shareable links are disabled
			if (route.query.errorpublic_shareable_links === "true") {
				push.error(t("loginView.errorpublic_shareable_links"));
			}
		});

		// Return the variables
		return {
			username,
			password,
			submitForm,
			t,
		};
	},
};
</script>
