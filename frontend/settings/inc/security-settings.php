<?php
    // Load the language file based on the user's preferred language
    switch ($_SESSION["preferred_language"]) {
        case 'en':
            $translationsSettingsSecuritySettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/security-settings/en.php';
            break;
        case 'pt':
            $translationsSettingsSecuritySettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/security-settings/pt.php';
            break;
        // ...
        default:
            $translationsSettingsSecuritySettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/security-settings/en.php';
    }

    $editUserPasswordAction = -9000;

    if (isset($_POST["editUserPassword"]) && $_GET["editUserPassword"] == 1) {
        if($_POST["passUserEdit"] == $_POST["passRepeatUserEdit"]){
            // Check password complexity
            if (preg_match('/^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$/', $_POST["passUserEdit"])) {
                $editUserPasswordAction = editUserPassword($_SESSION["id"], $_POST["passUserEdit"]);
            }else{
                $editUserPasswordAction = -4;
            }
        }else{
            $editUserPasswordAction = -3;
        }
    }

?>

<!-- Error banners -->
<?php if ($editUserPasswordAction == -1 || $editUserPasswordAction == -2 || $editUserPasswordAction == -3 || $editUserPasswordAction == -4) { ?>
    <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
        <i class="fa-solid fa-circle-exclamation me-1"></i>
        <div>
            <?php if ($editUserPasswordAction == -1) { ?>
                API ERROR | <?php echo $translationsSettings['settings_API_error_-1']; ?> (-1).
            <?php } else { ?>
                <?php if ($editUserPasswordAction == -2) { ?>
                    API ERROR | <?php echo $translationsSettings['settings_API_error_-2']; ?> (-2).
                <?php } else { ?>
                    <?php if ($editUserPasswordAction == -3) { ?>
                        <?php echo $translationsSettingsSecuritySettings['settings_security_settings_error_passwords_dont_match-3']; ?> (-3).
                    <?php }else{ ?>
                        <?php if ($editUserPasswordAction == -4) { ?>
                            <?php echo $translationsSettingsSecuritySettings['settings_security_settings_error_password_complexity-4']; ?> (-4).
                        <?php } ?>
                    <?php } ?>
                <?php } ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    </div>
<?php } ?>

<!-- Info banners -->

<!-- Success banners -->
<?php if ($editUserPasswordAction == 0) { ?>
    <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
        <div>
            <i class="fa-regular fa-circle-check me-1"></i>
            <?php if ($editUserPasswordAction == 0) { ?>
                <?php echo $translationsSettingsSecuritySettings['settings_security_settings_success_password_edited']; ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    </div>
<?php } ?>

<h4><?php echo $translationsSettingsSecuritySettings['settings_security_settings_subtitle_change_password']; ?></h4>

<!-- info banner to display password complexity requirements -->
<div class="alert alert-info alert-dismissible d-flex align-items-center" role="alert">
    <!--<i class="fa-solid fa-circle-info me-1 allign-top"></i>-->
    <div>
        <?php echo $translationsSettingsSecuritySettings['settings_security_settings_info_password_requirements']; ?>
        <br>
        <?php echo $translationsSettingsSecuritySettings['settings_security_settings_info_password_requirements_characters']; ?>
        <br>
        <?php echo $translationsSettingsSecuritySettings['settings_security_settings_info_password_requirements_capital_letters']; ?>
        <br>
        <?php echo $translationsSettingsSecuritySettings['settings_security_settings_info_password_requirements_numbers']; ?>
        <br>
        <?php echo $translationsSettingsSecuritySettings['settings_security_settings_info_password_requirements_special_characters']; ?>
    </div>
</div>

<form action="../settings/settings.php?editUserPassword=1&securitySettings=1" method="post" enctype="multipart/form-data">
    <!-- password fields -->
    <label for="passUserEdit"><b>* <?php echo $translationsSettingsSecuritySettings['settings_security_settings_subtitle_change_password_password']; ?></b></label>
    <input class="form-control" type="password" name="passUserEdit" placeholder="<?php echo $translationsSettingsSecuritySettings['settings_security_settings_subtitle_change_password_password']; ?>" value="<?php echo isset($_POST["passUserEdit"]) ? $_POST["passUserEdit"] : ''; ?>" required>

    <!-- repeat password fields -->
    <label class="mt-1" for="passRepeatUserEdit"><b>* <?php echo $translationsSettingsSecuritySettings['settings_security_settings_subtitle_change_password_repeat_password']; ?></b></label>
    <input class="form-control" type="password" name="passRepeatUserEdit" placeholder="<?php echo $translationsSettingsSecuritySettings['settings_security_settings_subtitle_change_password_repeat_password']; ?>" value="<?php echo isset($_POST["passRepeatUserEdit"]) ? $_POST["passRepeatUserEdit"] : ''; ?>" required>

    <p class="mt-1">* <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?></p>

    <button type="submit" class="btn btn-success" name="editUserPassword"><?php echo $translationsSettingsSecuritySettings['settings_security_settings_subtitle_change_password_button']; ?></button>
</form>