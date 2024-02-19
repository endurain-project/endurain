<template>
  <div class="form-signin w-100 m-auto text-center p-5" style="max-width: 500px">
    <!-- Error alerts -->
    <ErrorAlertComponent v-if="errorMessage"/>

    <!-- Info banners -->
    <InfoAlertComponent v-if="showSessionExpiredMessage"/>

    <form @submit.prevent="submitForm">
        <h1>Endurain</h1>
        <p>{{ $t("login.subtitle") }}</p>
        <br>

        <div class="form-floating">
            <input type="text" class="form-control" id="floatingInput" placeholder="<?php echo $translationsLogin['login_insert_username']; ?>" name="loginUsername" v-model="username" required>
            <label for="loginUsername">{{ $t("login.username") }}</label>
        </div>
        <br>
        <div class="form-floating">
            <input type="password" class="form-control" placeholder="<?php echo $translationsLogin['login_password']; ?>" name="loginPassword" v-model="password" required>
            <label for="loginPassword">{{ $t("login.password") }}</label>
        </div>
        <br>
        <div class="form-check">
            <input type="checkbox" class="form-check-input" name="loginNeverExpires" v-model="neverExpires">
            <label class="form-check-label" for="loginNeverExpires">{{ $t("login.neverExpires") }}</label>
        </div>
        <br>
        <button class="w-100 btn btn-lg btn-primary" type="submit">{{ $t("login.signInButton") }}</button>
        <!--<div>
            <br>
            <p>{{ $t("login.signUpText") }}</p>
            <button class="w-100 btn btn-lg btn-primary disabled" type="submit">{{ $t("login.signUpButton") }}></button>
        </div>-->
    </form>
  </div>
</template>

<script>
// Importing the vue composition API
import { ref, onMounted } from 'vue';
// Importing the router
import { useRoute, useRouter } from 'vue-router';
// Importing the i18n
import { useI18n } from 'vue-i18n';
// Importing the stores
import { useErrorAlertStore } from '@/stores/Alerts/errorAlert';
import { useInfoAlertStore } from '@/stores/Alerts/infoAlert';
// Importing the services for the login
import { auth } from '@/services/auth';
// Importing the components
import ErrorAlertComponent from '@/components/Alerts/ErrorAlertComponent.vue';
import InfoAlertComponent from '@/components/Alerts/InfoAlertComponent.vue';
// Importing the crypto-js
import CryptoJS from 'crypto-js';


// Exporting the default object
export default {
  // Components
  components: {
    ErrorAlertComponent,
    InfoAlertComponent,
  },
  // Setup function
  setup() {
    // Variables
    const route = useRoute();
    const router = useRouter();
    const { t } = useI18n();
    const username = ref('');
    const password = ref('');
    const neverExpires = ref(false);
    const errorMessage = ref('');
    const showSessionExpiredMessage = ref(false);
    const errorAlertStore = useErrorAlertStore();
    const infoAlertStore = useInfoAlertStore();

    // Handle the form submission
    const submitForm = async () => {
      // Hash the password
      const hashedPassword = CryptoJS.SHA256(password.value).toString(CryptoJS.enc.Hex);
      // Create the form data
      const formData = new URLSearchParams();
      formData.append('username', username.value);
      formData.append('password', hashedPassword);
      formData.append('neverExpires', neverExpires.value);

      try {
        // Get the token
        const token = await auth.getToken(formData);
        // Get the userMe
        const userMe = await auth.getUserMe(token.access_token);

        // Store the logged user
        auth.storeLoggedUser(token, userMe);
        // Redirect to the home page
        router.push('/');
      } catch (error) {
        // Handle the error
        if (error.toString().includes('401')) {
          errorMessage.value = t("login.error401") + " (401)";
          errorAlertStore.setAlertMessage(errorMessage.value);
        } else if (error.toString().includes('403')) {
          errorMessage.value = t("login.error403") + " (403)";
          errorAlertStore.setAlertMessage(errorMessage.value);
        } else if (error.toString().includes('500')) {
          errorMessage.value = t("login.error500") + " (500)";
          errorAlertStore.setAlertMessage(errorMessage.value);
        } else {
          errorMessage.value = t("login.errorUndefined") + " (Undefined)";
          errorAlertStore.setAlertMessage(errorMessage.value);
        }
      }
    };

    onMounted(() => {
      // Check if the session expired
      if (route.query.sessionExpired === 'true') {
        // Show the session expired message
        showSessionExpiredMessage.value = true;
        infoAlertStore.setAlertMessage(t("login.sessionExpired"));
      }
    });

    // Return the variables
    return {
      username,
      password,
      neverExpires,
      showSessionExpiredMessage,
      errorMessage,
      submitForm,
      t,
    };
  },
};
</script>
