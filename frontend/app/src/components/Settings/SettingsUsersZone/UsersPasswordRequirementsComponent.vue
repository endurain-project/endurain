<template>
  <!-- info banner to display password complexity requirements -->
  <div class="alert alert-info alert-dismissible d-flex align-items-center" role="alert">
    <!--<i class="fa-solid fa-circle-info me-1 allign-top"></i>-->
    <div>
      {{ $t('usersPasswordRequirementsComponent.passwordRequirementsTitle') }}
      <br />
      {{ $t('usersPasswordRequirementsComponent.passwordCharacters') }}
      <br />
      {{ $t('usersPasswordRequirementsComponent.passwordCapitalLetters') }}
      <br />
      {{ $t('usersPasswordRequirementsComponent.passwordNumbers') }}
      <br />
      {{ $t('usersPasswordRequirementsComponent.passwordSpecialCharacters') }}
    </div>
  </div>
</template>
