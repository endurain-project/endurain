<template>
  <div class="form-signin w-100 m-auto text-center p-5" style="max-width: 500px">
    <h1 class="fw-bolder">404</h1>
    <h3 class="mt-4">{{ $t('notFound.title') }}</h3>
    <h6>{{ $t('notFound.subTitle') }}</h6>

    <router-link :to="{ name: 'home' }" type="button" class="mt-4 btn btn-primary">
      {{ $t('notFound.backToHomeButton') }}
    </router-link>
  </div>
</template>
