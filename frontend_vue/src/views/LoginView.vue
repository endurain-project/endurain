<template>
  <div class="form-signin w-100 m-auto text-center p-5" style="max-width: 500px">
    <!-- Error alerts -->
    <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert" v-if="errorCode">
      <font-awesome-icon :icon="['fas', 'fa-circle-exclamation']" />
      <div class="ms-1">
        <span v-if="errorCode === '401'">{{ $t("login.error401") }} (401)</span>
        <span v-else-if="errorCode === '403'">{{ $t("login.error403") }} (403)</span>
        <span v-else-if="errorCode === '500'">{{ $t("login.error500") }} (500)</span>
        <span v-else>{{ $t("login.errorUndefined") }} (Undefined)</span>
        <!--<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>-->
      </div>
    </div>

    <!-- Info banners -->
    <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert" v-if="showSessionExpiredMessage">
      <font-awesome-icon :icon="['fas', 'fa-triangle-exclamation']" />
      <div class="ms-1">
        <span>{{ $t("login.sessionExpired") }}</span>
        <!--<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>-->
      </div>
    </div>

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
import CryptoJS from 'crypto-js';

import { auth } from '@/services/auth';

export default {
  data() {
    return {
      username: '',
      password: '',
      neverExpires: false,
      errorCode: '',
      showSessionExpiredMessage: false
    };
  },
  created() {
    if (this.$route.query.sessionExpired === 'true') {
      this.showSessionExpiredMessage = true;
    }
  },
  methods: {
    async submitForm() {
      // Hash the password using SHA-256
      const hashedPassword = CryptoJS.SHA256(this.password).toString(CryptoJS.enc.Hex);
      
      const formData = new URLSearchParams();
      formData.append('username', this.username);
      formData.append('password', hashedPassword);
      formData.append('neverExpires', this.neverExpires);

      try {
        const token = await auth.getToken(formData);
        const userMe = await auth.getUserMe(token.access_token);

        auth.storeLoggedUser(token, userMe);

        this.$router.push('/');
      } catch (error) {
        if (error.toString().includes('401')) {
          this.errorCode = '401';
        } else if (error.toString().includes('403')) {
          this.errorCode = '403';
        } else if (error.toString().includes('500')) {
          this.errorCode = '500';
        } else {
          this.errorCode = 'undefined';
        }
      }
    }
  }
};
</script>