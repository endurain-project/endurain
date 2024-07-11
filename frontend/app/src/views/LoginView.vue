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
        <!--<div class="form-check">
            <input type="checkbox" class="form-check-input" name="loginNeverExpires" v-model="neverExpires">
            <label class="form-check-label" for="loginNeverExpires">{{ $t("loginView.neverExpires") }}</label>
        </div>
        <br>-->
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
import { ref, onMounted } from 'vue';
// Importing the router
import { useRoute, useRouter } from 'vue-router';
// Importing the i18n
import { useI18n } from 'vue-i18n';
// Importing the utils
import { addToast } from '@/utils/toastUtils';
// Importing the stores
import { useAuthStore } from '@/stores/authStore';
// Importing the services for the login
import { session } from '@/services/sessionService';
import { users } from '@/services/usersService';


// Exporting the default object
export default {
  // Setup function
  setup() {
    // Variables
    const route = useRoute();
    const router = useRouter();
    const { locale, t } = useI18n();
    const username = ref('');
    const password = ref('');
    //const neverExpires = ref(false);
    const authStore = useAuthStore();

    // Handle the form submission
    const submitForm = async () => {
      // Create the form data
      const formData = new URLSearchParams();
      formData.append('grant_type', 'password');
      formData.append('username', username.value);
      formData.append('password', password.value);
      //formData.append('neverExpires', neverExpires.value);

      try {
        // Get the token
        await session.authenticateUser(formData);

        // Get logged user information
        const userMe = await users.getUserMe();

        // Store the user in the auth store
        authStore.setUser(userMe, locale);
        
        // Redirect to the home page
        router.push('/');
      } catch (error) {
        console.log(error);
        // Handle the error
        if (error.toString().includes('401')) {
          addToast(t('loginView.error401') + " (401)", 'danger', true);
        } else if (error.toString().includes('403')) {
          addToast(t('loginView.error403') + " (403)", 'danger', true);
        } else if (error.toString().includes('500')) {
          addToast(t('loginView.error500') + " (500)", 'danger', true);
        } else {
          addToast(t('loginView.errorUndefined') + " (Undefined)", 'danger', true);
        }
      }
    };

    onMounted(() => {
      // Check if the session expired
      if (route.query.sessionExpired === 'true') {
        addToast(t('loginView.sessionExpired'), 'warning', true);
      }
    });

    // Return the variables
    return {
      username,
      password,
      //neverExpires,
      submitForm,
      t,
    };
  },
};
</script>
