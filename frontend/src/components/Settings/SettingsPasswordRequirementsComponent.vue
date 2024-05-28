<template>
    <!-- info banner to display password complexity requirements -->
    <div class="alert alert-info alert-dismissible d-flex align-items-center" role="alert">
        <!--<i class="fa-solid fa-circle-info me-1 allign-top"></i>-->
        <div>
            {{ $t("usersListComponent.modalChangeUserPasswordPasswordRequirementsTitle") }}
            <br>
            {{ $t("usersListComponent.modalChangeUserPasswordCharacters") }}
            <br>
            {{ $t("usersListComponent.modalChangeUserPasswordCapitalLetters") }}
            <br>
            {{ $t("usersListComponent.modalChangeUserPasswordNumbers") }}
            <br>
            {{ $t("usersListComponent.modalChangeUserPasswordSpecialCharacters") }}
        </div>
    </div>
</template>