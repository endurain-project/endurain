<?php
    // Load the language file based on the user's preferred language
    switch ($_SESSION["preferred_language"]) {
        case 'en':
            $translationsSettingsProfileSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/profile-settings/en.php';
            break;
        case 'pt':
            $translationsSettingsProfileSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/profile-settings/pt.php';
            break;
        // ...
        default:
            $translationsSettingsProfileSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/profile-settings/en.php';
    }

    // profile
    $editProfileAction = -9000;
    $deletePhotoProfileAction = -9000;

    // User profile section
    /* Edit action */
    if (isset($_POST["editProfile"])) {
        if (empty(trim($_POST["profileNameEdit"]))) {
            $_POST["profileNameEdit"] = NULL;
        }else{
            $_POST["profileNameEdit"] = trim($_POST["profileNameEdit"]);
        }

        if (empty(trim($_POST["profileBirthDateEdit"]))) {
            $_POST["profileBirthDateEdit"] = NULL;
        }

        if (empty(trim($_POST["profileCityEdit"]))) {
            $_POST["profileCityEdit"] = NULL;
        }else{
            $_POST["profileCityEdit"] = trim($_POST["profileCityEdit"]);
        }

        if (isset($_FILES["profileImgEdit"]) && $_FILES["profileImgEdit"]["error"] == 0) {
            $target_dir = "../img/users_img/";

            // Create the directory if it doesn't exist
            if (!file_exists($target_dir)) {
                mkdir($target_dir, 0755, true);
            }
            
            $info = pathinfo($_FILES["profileImgEdit"]["name"]);
            $ext = $info['extension']; // get the extension of the file
            #$newname = $_GET["userID"].".".$ext;
            $newname = "img_" . rand(1, 20) . "_" . rand(1, 9999999) . "_" . rand(1, 20) . "." . $ext;
            $target_file = $target_dir . $newname;
            $uploadOk = 1;
            $imageFileType = strtolower(pathinfo($target_file, PATHINFO_EXTENSION));
            // Check if image file is a actual image or fake image
            $check = getimagesize($_FILES["profileImgEdit"]["tmp_name"]);
            if ($check !== false) {
                $uploadOk = 1;
            } else {
                $editProfileAction = -3;
                $uploadOk = 0;
            }
            // Allow certain file formats
            if ($imageFileType != "jpg" && $imageFileType != "png" && $imageFileType != "jpeg") {
                $editProfileAction = -4;
                $uploadOk = 0;
            }
            // Check if $uploadOk is set to 0 by an error
            if ($uploadOk == 1) {
                if(getUserPhotoAuxFromID($_SESSION["id"]) != null){
                    if (unlink(getUserPhotoAuxFromID($_SESSION["id"]))) {
                        unsetUserPhoto($_SESSION["id"]);
                    }
                }
                if (move_uploaded_file($_FILES["profileImgEdit"]["tmp_name"], $target_file)) {
                    $photoPath = "..\img\users_img\\" . $newname;
                    $photoPath_aux = $target_file;
                    $editProfileAction = editUser($_POST["profileNameEdit"], trim($_POST["profileUsernameEdit"]), trim($_POST["profileEmailEdit"]), $_SESSION["id"], $_POST["profilePreferredLanguageEdit"], $_POST["profileCityEdit"], $_POST["profileBirthDateEdit"], $_POST["profileGenderEdit"], $_SESSION["access_type"], $photoPath, $photoPath_aux, 1);
                    setUserRelatedInfoSession($_SESSION["token"]);
                } else {
                    $editProfileAction = -5;
                    $uploadOk = 0;
                }
            }
        } else {
            $profilePhoto = getUserPhotoFromID($_SESSION["id"]);
            $profilePhotoAux = getUserPhotoAuxFromID($_SESSION["id"]);
            $editProfileAction = editUser($_POST["profileNameEdit"], trim($_POST["profileUsernameEdit"]), trim($_POST["profileEmailEdit"]), $_SESSION["id"], $_POST["profilePreferredLanguageEdit"], $_POST["profileCityEdit"], $_POST["profileBirthDateEdit"], $_POST["profileGenderEdit"], $_SESSION["access_type"], $profilePhoto, $profilePhotoAux, 1);
            setUserRelatedInfoSession($_SESSION["token"]);
        }
    }

    /* Delete user photo */
    if (isset($_GET["deleteProfilePhoto"]) && $_GET["deleteProfilePhoto"] == 1) {
        if (unlink(getUserPhotoAuxFromID($_SESSION["id"]))) {
            $deletePhotoProfileAction = unsetUserPhoto($_SESSION["id"]);
            if ($deletePhotoProfileAction == 0) {
                $_SESSION["photo_path"] = NULL;
                $_SESSION["photo_path_aux"] = NULL;
            }
        } else {
            $deletePhotoProfileAction = -3;
        }
    }
?>

<!-- Error banners -->
<?php if ($deletePhotoProfileAction == -1 || $deletePhotoProfileAction == -2 || $deletePhotoProfileAction == -3 || $editProfileAction == -1 || $editProfileAction == -2 || $editProfileAction == -3 || $editProfileAction == -4 || $editProfileAction == -5) { ?>
    <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
        <i class="fa-solid fa-circle-exclamation me-1"></i>
        <div>
            <?php if ($deletePhotoProfileAction == -1 || $editProfileAction == -1) { ?>
                API ERROR | <?php echo $translationsSettings['settings_API_error_-1']; ?> (-1).
            <?php } else { ?>
                <?php if ($deletePhotoProfileAction == -2 || $editProfileAction == -2) { ?>
                    API ERROR | <?php echo $translationsSettings['settings_API_error_-2']; ?> (-2).
                <?php } else { ?>
                    <?php if ($deletePhotoProfileAction == -3) { ?>
                        <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_error_deleteProfilePhoto_-3']; ?> (-3).
                    <?php } else { ?>
                        <?php if ($editProfileAction == -3) { ?>
                            <?php echo $translationsSettingsProfileSettings['settings_profile_settings_error_editProfile_-3']; ?> (-3).
                        <?php } else { ?>
                            <?php if ($editProfileAction == -4) { ?>
                                <?php echo $translationsSettingsProfileSettings['settings_profile_settings_error_editProfile_-4']; ?> (-4).
                            <?php } else { ?>
                                <?php if ($editProfileAction == -5) { ?>
                                    <?php echo $translationsSettingsProfileSettings['settings_profile_settings_error_editProfile_-5']; ?> (-5).
                                <?php } ?>
                            <?php } ?>
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
<?php if ($deletePhotoProfileAction == 0 || $editProfileAction == 0 || (isset($_GET["stravaLinked"]) && $_GET["stravaLinked"] == 1)) { ?>
    <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
        <div>
            <i class="fa-regular fa-circle-check me-1"></i>
            <?php if ($deletePhotoProfileAction == 0) { ?>
                <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_success_profilePhotoDeleted']; ?>
            <?php } else { ?>
                <?php if ($editProfileAction == 0) { ?>
                    <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_success_profileEdited']; ?>
                <?php } else { ?>
                    <?php if (isset($_GET["stravaLinked"]) && $_GET["stravaLinked"] == 1) { ?>
                        <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_success_stravaLinked']; ?>
                    <?php } ?>
                <?php } ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    </div>
<?php } ?>

<!-- Profile photo and buttons zone -->
<div class="row row-gap-3">
    <div class="col-lg-4 col-md-12">
        <div class="justify-content-center align-items-center d-flex">
            <img src=<?php if (is_null($_SESSION["photo_path"])) {
                if ($_SESSION["gender"] == 1) {
                    echo ("../img/avatar/male1.png");
                } else {
                    echo ("../img/avatar/female1.png");
                }
            } else {
                echo ($_SESSION["photo_path"]);
            } ?> alt="Profile picture" width="180" height="180" class="rounded-circle">
        </div>

        <!-- Delete profile photo section -->
        <?php if (!is_null($_SESSION["photo_path"])) { ?>
            <a class="mt-4 w-100 btn btn-danger" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteProfilePhotoModal"><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_deleteProfilePhoto']; ?></a>
        <?php } ?>

        <!-- Modal delete profile photo -->
        <div class="modal fade" id="deleteProfilePhotoModal" tabindex="-1" aria-labelledby="deleteProfilePhotoModal" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5" id="deleteProfilePhotoModal"><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_modal_title_deleteProfilePhoto']; ?></h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_modal_body_deleteProfilePhoto']; ?>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                        <a type="button" class="btn btn-danger" href="../settings/settings.php?deleteProfilePhoto=1&profileSettings=1"><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_modal_title_deleteProfilePhoto']; ?></a>
                    </div>
                </div>
            </div>
        </div>

        <!-- Edit profile section -->
        <a class="mt-2 w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editProfileModal<?php echo ($_SESSION["id"]); ?>"><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_button_editprofile']; ?></a>

        <!-- Modal edit profile -->
        <div class="modal fade" id="editProfileModal<?php echo ($_SESSION["id"]); ?>" tabindex="-1" aria-labelledby="editProfileModal<?php echo ($_SESSION["id"]); ?>" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5" id="editProfileModal<?php echo ($_SESSION["id"]); ?>"><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_editProfile_title']; ?></h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <form action="../settings/settings.php?editProfile=1&profileSettings=1" method="post" enctype="multipart/form-data">
                        <div class="modal-body">
                            <label for="profileImgEdit"><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_photo_label']; ?></b></label>
                            <div>
                                <div class="row">
                                    <div class="col">
                                        <input class="form-control" type="file" accept="image/*" name="profileImgEdit" id="profileImgEdit" value="<?php echo ($_SESSION["photo_path"]); ?>">
                                    </div>
                                </div>
                            </div>
                            <!-- username fields -->
                            <label for="profileUsernameEdit"><b>* <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_username_label']; ?></b></label>
                            <input class="form-control" type="text" name="profileUsernameEdit" placeholder="<?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_username_placeholder']; ?>" maxlength="250" value="<?php echo ($_SESSION["username"]); ?>" required>
                            <!-- name fields -->
                            <label for="profileNameEdit"><b>* <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_name_label']; ?></b></label>
                            <input class="form-control" type="text" name="profileNameEdit" placeholder="<?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_name_placeholder']; ?>" maxlength="250" value="<?php echo ($_SESSION["name"]); ?>" required>
                            <!-- email fields -->
                            <label for="profileEmailEdit"><b>* <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_email_label']; ?></b></label>
                            <input class="form-control" type="text" name="profileEmailEdit" placeholder="<?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_email_placeholder']; ?>" maxlength="45" value="<?php echo ($_SESSION["email"]); ?>" required>
                            <!-- city fields -->
                            <label for="profileCityEdit"><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_city_label']; ?></b></label>
                            <input class="form-control" type="text" name="profileCityEdit" placeholder="<?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_city_placeholder']; ?>" maxlength="45" value="<?php echo ($_SESSION["city"]); ?>">
                            <!-- birth date fields -->
                            <label for="profileBirthDateEdit"><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_birthdate_label']; ?></b></label>
                            <input class="form-control" type="date" name="profileBirthDateEdit" value="<?php echo ($_SESSION["birthdate"]); ?>">
                            <!-- gender fields -->
                            <label for="profileGenderEdit"><b>* <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_gender_label']; ?></b></label>
                            <select class="form-control" name="profileGenderEdit">
                                <option value="1" <?php if ($_SESSION["gender"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_gender_option1']; ?></option>
                                <option value="2" <?php if ($_SESSION["gender"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_gender_option2']; ?></option>
                            </select required>
                            <!-- preferred language fields -->
                            <label for="profilePreferredLanguageEdit"><b>* <?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_preferredLanguage_label']; ?></b></label>
                            <select class="form-control" name="profilePreferredLanguageEdit">
                                <option value="en" <?php if ($_SESSION["preferred_language"] == "en") { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_preferredLanguage_option1']; ?></option>
                                <option value="pt" <?php if ($_SESSION["preferred_language"] == "pt") { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_preferredLanguage_option2']; ?></option>
                            </select required>

                            * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                            <button type="submit" class="btn btn-success" name="editProfile"><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_editProfile_title']; ?></button>
                        </div>
                    </form>
                </div>
            </div>
        </div>

        <!-- Strava button 
        <?php if ($_SESSION["is_strava_linked"] == 1) { ?>
            <div class="mt-2">
                <span class="fs-6">Strava already linked</span>
            </div>
        <?php } ?>
        <a class="mt-2 w-100 btn <?php if ($_SESSION["is_strava_linked"] == 1) {
            echo 'disabled';
        } ?>" style="--bs-btn-bg: #FC4C02; --bs-btn-active-bg: #FC4C02; --bs-btn-hover-bg: #FC4C02; --bs-btn-disabled-bg: #FC4C02; --bs-btn-disabled-border-color: #FC4C02;" href="../settings/settings.php?profileSettings=1&linkStrava=1" <?php if ($_SESSION["is_strava_linked"] == 1) {
                echo 'aria-disabled="true"';
            } ?> role="button"><img src="../img/strava/btn_strava_connectwith_orange.png" alt="Link with strava button" width="65%" height="65%"></a>-->
    </div>

    <!-- Profile attributes -->
    <div class="col">
        <h2><?php echo ($_SESSION["name"]); ?></h2>
        <p><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_username_subtitle']; ?></b><?php echo ($_SESSION["username"]); ?></p>
        <p><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_email_subtitle']; ?></b><?php echo ($_SESSION["email"]); ?></p>
        <p><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_birthdate_subtitle']; ?></b><?php
            if (isset($_SESSION["birthdate"]) && !empty($_SESSION["birthdate"])) {
                echo date("d/m/Y", strtotime($_SESSION["birthdate"]));
            } else {
                echo "N/A"; // Or any default value you prefer when birthdate is not set
            }
            ?></p>
        <p><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_city_subtitle']; ?></b><?php
            if (isset($_SESSION["city"]) && !empty($_SESSION["city"])) {
                echo $_SESSION["city"];
            } else {
                echo "N/A"; // Or any default value you prefer when birthdate is not set
            }
            ?></p>
        <p><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_gender_subtitle']; ?></b><?php if ($_SESSION["gender"] == 1) {
                echo $translationsSettingsProfileSettings['settings_sidebar_profile_gender_male'];
            } else {
                echo $translationsSettingsProfileSettings['settings_sidebar_profile_gender_female'];
            } ?></p>
        <p><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_preferredlanguage_subtitle']; ?></b><?php echo ($_SESSION["preferred_language"]); ?></p>
        <p><b><?php echo $translationsSettingsProfileSettings['settings_sidebar_profile_access_type_subtitle']; ?></b> <?php if ($_SESSION["access_type"] == 1) {
                echo $translationsSettingsProfileSettings['settings_sidebar_profile_access_type_regular_user'];
            } else {
                if ($_SESSION["access_type"] == 2) {
                    echo $translationsSettingsProfileSettings['settings_sidebar_profile_access_type_admin'];
                } else {
                    if ($_SESSION["access_type"] == 3) {
                        echo $translationsSettingsProfileSettings['settings_sidebar_profile_access_type_teacher'];
                    } else {
                        echo $translationsSettingsProfileSettings['settings_sidebar_profile_access_type_parent'];
                    }
                }
            } ?>
    </div>
</div>