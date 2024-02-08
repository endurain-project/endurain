<?php
    // Load the language file based on the user's preferred language
    switch ($_SESSION["preferred_language"]) {
        case 'en':
            $translationsSettingsUsersSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/users-settings/en.php';
            break;
        case 'pt':
            $translationsSettingsUsersSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/users-settings/pt.php';
            break;
        // ...
        default:
            $translationsSettingsUsersSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/users-settings/en.php';
    }

    # Users section
    // users
    $numUsers = 0;
    $users = [];
    $addUserAction = -9000;
    $photoDeleted = -9000;
    $deleteAction = -9000;
    $deletePhotoUserAction = -9000;
    $editUserAction = -9000;
    $pageNumberUsers = 1;

    /* Add user action */
    if (isset($_POST["addUser"]) && $_GET["addUser"] == 1) {
        if (empty(trim($_POST["userNameAdd"]))) {
            $_POST["userNameAdd"] = NULL;
        }

        if (isset($_FILES["userImgAdd"]) && $_FILES["userImgAdd"]["error"] == 0) {
            $target_dir = "../img/users_img/";

            // Create the directory if it doesn't exist
            if (!file_exists($target_dir)) {
                mkdir($target_dir, 0755, true);
            }

            $info = pathinfo($_FILES["userImgAdd"]["name"]);
            $ext = $info['extension']; // get the extension of the file
            #$number=lastIdUsers()+1;
            $newname = "img_" . rand(1, 20) . "_" . rand(1, 9999999) . "_" . rand(1, 20) . "." . $ext;
            $target_file = $target_dir . $newname;
            $uploadOk = 1;
            $imageFileType = strtolower(pathinfo($target_file, PATHINFO_EXTENSION));
            // Check if image file is a actual image or fake image
            $check = getimagesize($_FILES["userImgAdd"]["tmp_name"]);
            if ($check !== false) {
                $uploadOk = 1;
            } else {
                $addUserAction = -4;
                $uploadOk = 0;
            }
            // Allow certain file formats
            if ($imageFileType != "jpg" && $imageFileType != "png" && $imageFileType != "jpeg") {
                $addUserAction = -5;
                $uploadOk = 0;
            }
            // Check if $uploadOk is set to 0 by an error
            if ($uploadOk == 1) {
                if (move_uploaded_file($_FILES["userImgAdd"]["tmp_name"], $target_file)) {
                    $photoPath = "..\img\users_img\\" . $newname;
                    $photoPath_aux = $target_file;
                } else {
                    $addUserAction = -6;
                    $uploadOk = 0;
                }
            }
        } else {
            $photoPath = NULL;
            $photoPath_aux = NULL;
            $uploadOk = 1;
        }
        if ($uploadOk == 1) {
            $userCity = trim($_POST["userCityAdd"]);
            if (empty($userCity)) {
                $userCity = NULL;
            }
            if (empty($_POST["userBirthDateAdd"])) {
                $_POST["userBirthDateAdd"] = NULL;
            }

            $addUserAction = newUser(trim($_POST["userNameAdd"]), trim($_POST["userUsernameAdd"]), trim($_POST["userEmailAdd"]), $_POST["passUserAdd"], $_POST["userGenderAdd"], $_POST["userPreferredLanguageAdd"], $userCity, $_POST["userBirthDateAdd"], $_POST["userAccessTypeAdd"], $photoPath, $photoPath_aux, 1);
        }
    }

    /* Edit user action */
    if (isset($_POST["userEdit"])) {
        if (empty(trim($_POST["userNameEdit"]))) {
            $_POST["userNameEdit"] = NULL;
        }
        if (empty($_POST["userTypeEdit"])) {
            $_POST["userTypeEdit"] = NULL;
        }

        if (empty($_POST["userUsernameEdit"]) && empty($_POST["userTypeEdit"])) {
            $editAction = -3;
        } else {
            $userCity = trim($_POST["userCityEdit"]);
            if (empty($userCity)) {
                $userCity = NULL;
            }
            if (empty($_POST["userBirthDateEdit"])) {
                $_POST["userBirthDateEdit"] = NULL;
            }
            if (isset($_FILES["userImgEdit"]) && $_FILES["userImgEdit"]["error"] == 0) {
                $target_dir = "../img/users_img/";

                // Create the directory if it doesn't exist
                if (!file_exists($target_dir)) {
                    mkdir($target_dir, 0777, true);
                }
                
                $info = pathinfo($_FILES["userImgEdit"]["name"]);
                $ext = $info['extension']; // get the extension of the file
                #$newname = $_GET["userID"].".".$ext;
                $newname = "img_" . rand(1, 20) . "_" . rand(1, 9999999) . "_" . rand(1, 20) . "." . $ext;
                $target_file = $target_dir . $newname;
                $uploadOk = 1;
                $imageFileType = strtolower(pathinfo($target_file, PATHINFO_EXTENSION));
                // Check if image file is a actual image or fake image
                $check = getimagesize($_FILES["userImgEdit"]["tmp_name"]);
                if ($check !== false) {
                    $uploadOk = 1;
                } else {
                    $editUserAction = -4;
                    $uploadOk = 0;
                }
                // Allow certain file formats
                if ($imageFileType != "jpg" && $imageFileType != "png" && $imageFileType != "jpeg") {
                    $editUserAction = -5;
                    $uploadOk = 0;
                }
                // Check if $uploadOk is set to 0 by an error
                if ($uploadOk == 1) {
                    if(getUserPhotoAuxFromID($_GET["userID"]) != null){
                        if (unlink(getUserPhotoAuxFromID($_GET["userID"]))) {
                            unsetUserPhoto($_GET["userID"]);
                        }
                    }
                    if (move_uploaded_file($_FILES["userImgEdit"]["tmp_name"], $target_file)) {
                        $photoPath = "..\img\users_img\\" . $newname;
                        $photoPath_aux = $target_file;
                        $editUserAction = editUser(trim($_POST["userNameEdit"]), trim($_POST["userUsernameEdit"]), trim($_POST["userEmailEdit"]), $_GET["userID"], $_POST["userPreferredLanguageEdit"], $userCity, $_POST["userBirthDateEdit"], $_POST["userGenderEdit"], $_POST["userTypeEdit"], $photoPath, $photoPath_aux, $_POST["userIsActiveEdit"]);
                        if ($_GET["userID"] == $_SESSION["id"]) {
                            setUserRelatedInfoSession($_SESSION["token"]);
                        }
                    } else {
                        $editUserAction = -6;
                        $uploadOk = 0;
                    }
                }
            } else {
                $userPhoto = getUserPhotoFromID($_GET["userID"]);
                if (empty($userPhoto)) {
                    $userPhoto = NULL;
                }
                $userPhotoAux = getUserPhotoAuxFromID($_GET["userID"]);
                if (empty($userPhotoAux)) {
                    $userPhotoAux = NULL;
                }
                $editUserAction = editUser(trim($_POST["userNameEdit"]), trim($_POST["userUsernameEdit"]), trim($_POST["userEmailEdit"]), $_GET["userID"], $_POST["userPreferredLanguageEdit"], $userCity, $_POST["userBirthDateEdit"], $_POST["userGenderEdit"], $_POST["userTypeEdit"], $userPhoto, $userPhotoAux, $_POST["userIsActiveEdit"]);
                if ($_GET["userID"] == $_SESSION["id"]) {
                    setUserRelatedInfoSession($_SESSION["token"]);
                }
            }
        }
    }

    /* Delete user photo */
    if (isset($_GET["deletePhotoUser"]) && $_GET["deletePhotoUser"] == 1) {
        if (unlink(getUserPhotoAuxFromID($_GET["userID"]))) {
            $deletePhotoUserAction = unsetUserPhoto($_GET["userID"]);
            if ($_GET["userID"] == $_SESSION["id"]) {
                setUserRelatedInfoSession($_SESSION["token"]);
            }
        } else {
            $deletePhotoUserAction = -3;
        }
    }

    /* Delete user */
    if (isset($_GET["deleteUser"]) && $_GET["deleteUser"] == 1) {
        if ($_GET["userID"] != $_SESSION["id"]) {
            $photo_path = getUserPhotoAuxFromID($_GET["userID"]);
            $deleteAction = deleteUser($_GET["userID"]);
            if ($deleteAction == 0) {
                if (!is_null($photo_path)) {
                    if (unlink($photo_path)) {
                        $photoDeleted = 0;
                    } else {
                        $photoDeleted = 1;
                    }
                } else {
                    $photoDeleted = 2;
                }
            }
        } else {
            $deleteAction = -3;
        }
    }

    if (isset($_GET["pageNumberUsers"])) {
        $pageNumberUsers = $_GET["pageNumberUsers"];
    }

    if (!isset($_POST["userSearch"])) {
        $users = getUsersPagination($pageNumberUsers, $numRecords);
        $numUsers = numUsers();
        $total_pages = ceil($numUsers / $numRecords);
    } else {
        $users = getUsersIfContainsUsername(urlencode(trim($_POST["userUsername"])));
        if ($users == NULL) {
            $numUsers = 0;
        } else {
            $numUsers = 1;
        }
    }

    // edit user password
    $editUserPasswordAdminAction = -9000;

    if (isset($_POST["editUserPasswordAdmin"]) && $_GET["editUserPasswordAdmin"] == 1) {
        if(isset($_GET["userID"]) && $_GET["userID"] > 0){
            if($_POST["passUserEditAdmin"] == $_POST["passRepeatUserEditAdmin"]){
                // Check password complexity
                if (preg_match('/^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+])[A-Za-z\d!@#$%^&*()_+]{8,}$/', $_POST["passUserEditAdmin"])) {
                    $editUserPasswordAdminAction = editUserPassword($_GET["userID"], $_POST["passUserEditAdmin"]);
                }else{
                    $editUserPasswordAdminAction = -4;
                }
            }else{
                $editUserPasswordAdminAction = -3;
            }
        }else{
            $editUserPasswordAdminAction = -5;
        }
    }
?>

<!-- Error banners -->
<?php if ($users == -1 || $users == -2 || $editUserAction == -1 || $editUserAction == -2 || $editUserAction == -3 || $editUserAction == -4 || $editUserAction == -5 || $editUserAction == -6 || $deleteAction == -1 || $deleteAction == -2 || $deleteAction == -409 || $deleteAction == -3 || $addUserAction == -1 || $addUserAction == -2 || $addUserAction == -3 || $addUserAction == -4 || $addUserAction == -5 || $addUserAction == -6 || $deletePhotoUserAction == -1 || $deletePhotoUserAction == -2 || $deletePhotoUserAction == -3 || $editUserPasswordAdminAction == -1 || $editUserPasswordAdminAction == -2 || $editUserPasswordAdminAction == -3 || $editUserPasswordAdminAction == -4 || $editUserPasswordAdminAction == -5) { ?>
    <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
        <i class="fa-solid fa-circle-exclamation me-1"></i>
        <div>
            <?php if ($users == -1 || $addUserAction == -1 || $editUserAction == -1 || $deletePhotoUserAction == -1 || $deleteAction == -1) { ?>
                API ERROR | <?php echo $translationsSettings['settings_API_error_-1']; ?> (-1).
            <?php } else { ?>
                <?php if ($users == -2 || $addUserAction == -2 || $editUserAction == -2 || $deletePhotoUserAction == -2 || $deleteAction == -2) { ?>
                API ERROR | <?php echo $translationsSettings['settings_API_error_-2']; ?> (-2).
                <?php } else { ?>
                    <?php if ($editUserAction == -3) { ?>
                        <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_editUser_-3']; ?> (-3).
                    <?php } else { ?>
                        <?php if ($editUserAction == -4) { ?>
                            <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_addEditUser_-4']; ?> (-4).
                        <?php } else { ?>
                            <?php if ($editUserAction == -5) { ?>
                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_addEditUser_-5']; ?> (-5).
                            <?php } else { ?>
                                <?php if ($editUserAction == -6) { ?>
                                    <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_addEditUser_-6']; ?> (-6).
                                <?php } else { ?>
                                    <?php if ($deleteAction == -3) { ?>
                                        <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_deleteUser_-3']; ?> (-3).
                                    <?php } else { ?>
                                        <?php if ($deleteAction == -409) { ?>
                                            <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_deleteUser_-409']; ?> (-3).
                                        <?php } else { ?>
                                            <?php if ($addUserAction == -3) { ?>
                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_addUser_-3']; ?> (-3).
                                            <?php } else { ?>
                                                <?php if ($addUserAction == -4) { ?>
                                                    <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_addEditUser_-4']; ?> (-4).
                                                <?php } else { ?>
                                                    <?php if ($addUserAction == -5) { ?>
                                                        <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_addEditUser_-5']; ?> (-5).
                                                    <?php } else { ?>
                                                        <?php if ($addUserAction == -6) { ?>
                                                            <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_addEditUser_-6']; ?> (-6).
                                                        <?php } else { ?>
                                                            <?php if ($deletePhotoUserAction == -3) { ?>
                                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_deleteUserPhoto_-3']; ?> (-3).
                                                            <?php }else{ ?>
                                                                <?php if ($editUserPasswordAdminAction == -1) { ?>
                                                                    API ERROR | <?php echo $translationsSettings['settings_API_error_-1']; ?> (-1).
                                                                <?php } else { ?>
                                                                    <?php if ($editUserPasswordAdminAction == -2) { ?>
                                                                        API ERROR | <?php echo $translationsSettings['settings_API_error_-2']; ?> (-2).
                                                                    <?php } else { ?>
                                                                        <?php if ($editUserPasswordAdminAction == -3) { ?>
                                                                            <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_passwords_dont_match-3']; ?> (-3).
                                                                        <?php }else{ ?>
                                                                            <?php if ($editUserPasswordAdminAction == -4) { ?>
                                                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_password_complexity-4']; ?> (-4).
                                                                            <?php }else{ ?>
                                                                                <?php if ($editUserPasswordAdminAction == -4) { ?>
                                                                                    <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_user_id_not_valid-5']; ?> (-5).
                                                                                <?php } ?>
                                                                            <?php } ?>
                                                                        <?php } ?>
                                                                    <?php } ?>
                                                                <?php } ?>
                                                            <?php } ?>
                                                        <?php } ?>
                                                    <?php } ?>
                                                <?php } ?>
                                            <?php } ?>
                                        <?php } ?>
                                    <?php } ?>
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
<?php if ($users == NULL || ($deleteAction == 0 && $photoDeleted == 1)) { ?>
    <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
        <i class="fa-solid fa-triangle-exclamation me-1"></i>
        <div>
            <?php if ($users == NULL) { ?>
                <?php echo $translationsSettingsUsersSettings['settings_users_settings_error_searchUser_NULL']; ?> (NULL).
            <?php } else { ?>
                <?php if ($deleteAction == 0 && $photoDeleted == 1) { ?>
                    <?php echo $translationsSettingsUsersSettings['settings_users_settings_info_userDeleted_photoNotDeleted']; ?>
                <?php } ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    </div>
<?php } ?>

<!-- Success banners -->
<?php if ($addUserAction == 0 || $editUserAction == 0 || ($deleteAction == 0 && $photoDeleted == 0) || ($deleteAction == 0 && $photoDeleted == 2) || $deletePhotoUserAction == 0 || $editUserPasswordAdminAction == 0) { ?>
    <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
        <div>
            <i class="fa-regular fa-circle-check me-1"></i>
            <?php if ($addUserAction == 0) { ?>
                <?php echo $translationsSettingsUsersSettings['settings_users_settings_success_userAdded']; ?>
            <?php } else { ?>
                <?php if ($editUserAction == 0) { ?>
                    <?php echo $translationsSettingsUsersSettings['settings_users_settings_success_userEdited']; ?>
                <?php } else { ?>
                    <?php if (($deleteAction == 0 && $photoDeleted == 0) || ($deleteAction == 0 && $photoDeleted == 2)) { ?>
                        <?php echo $translationsSettingsUsersSettings['settings_users_settings_success_userDeleted']; ?>
                    <?php } else { ?>
                        <?php if ($deletePhotoUserAction == 0) { ?>
                            <?php echo $translationsSettingsUsersSettings['settings_users_settings_success_userPhotoDeleted']; ?>
                        <?php }else{ ?>
                            <?php if ($editUserPasswordAdminAction == 0) { ?>
                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_success_password_edited']; ?>
                            <?php } ?>
                        <?php } ?>
                    <?php } ?>
                <?php } ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    </div>
<?php } ?>

<div class="row row-gap-3">
    <div class="col-lg-4 col-md-12">
        <!-- add user button -->
        <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addUserModal"><?php echo $translationsSettingsUsersSettings['settings_sidebar_button_addUser']; ?></a>

        <!-- Modal add user -->
        <div class="modal fade" id="addUserModal" tabindex="-1" aria-labelledby="addUserModal" aria-hidden="true">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h1 class="modal-title fs-5" id="addUserModal"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addUser_title']; ?></h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <form action="../settings/settings.php?addUser=1&users=1" method="post" enctype="multipart/form-data">
                        <div class="modal-body">
                            <!-- img fields -->
                            <label for="userImgAdd"><b><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_photoLabel']; ?></b></label>
                            <input class="form-control" type="file" accept="image/*" name="userImgAdd" id="userImgAdd" value="<?php echo isset($_POST["userImgAdd"]) ? $_POST["userImgAdd"] : ''; ?>">
                            <!-- username fields -->
                            <label for="userUsernameAdd"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_usernameLabel']; ?></b></label>
                            <input class="form-control" type="text" name="userUsernameAdd" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_usernamePlaceholder']; ?>" maxlength="45" value="<?php echo isset($_POST["userUsernameAdd"]) ? htmlspecialchars($_POST["userUsernameAdd"]) : ''; ?>" required>
                            <!-- name fields -->
                            <label for="userNameAdd"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_nameLabel']; ?></b></label>
                            <input class="form-control" type="text" name="userNameAdd" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_namePlaceholder']; ?>" maxlength="45" value="<?php echo isset($_POST["userNameAdd"]) ? htmlspecialchars($_POST["userNameAdd"]) : ''; ?>" required>
                            <!-- email fields -->
                            <label for="userEmailAdd"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_emailLabel']; ?></b></label>
                            <input class="form-control" type="text" name="userEmailAdd" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_emailPlaceholder']; ?>" maxlength="45" value="<?php echo isset($_POST["userEmailAdd"]) ? htmlspecialchars($_POST["userEmailAdd"]) : ''; ?>" required>
                            <!-- password fields -->
                            <label for="passUserAdd"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_passwordLabel']; ?></b></label>
                            <input class="form-control" type="password" name="passUserAdd" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_passwordPlaceholder']; ?>" value="<?php echo isset($_POST["passUserAdd"]) ? $_POST["passUserAdd"] : ''; ?>" required>
                            <!-- city fields -->
                            <label for="userCityAdd"><b><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_cityLabel']; ?></b></label>
                            <input class="form-control" type="text" name="userCityAdd" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_cityPlaceholder']; ?>" maxlength="45" value="<?php echo isset($_POST["userCityAdd"]) ? htmlspecialchars($_POST["userCityAdd"]) : ''; ?>">
                            <!-- birth date fields -->
                            <label for="userBirthDateAdd"><b><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_birthdateLabel']; ?></b></label>
                            <input class="form-control" type="date" name="userBirthDateAdd" value="<?php echo isset($_POST["userBirthDateAdd"]) ? htmlspecialchars($_POST["userBirthDateAdd"]) : ''; ?>">
                            <!-- gender fields -->
                            <label for="userGenderAdd"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_genderLabel']; ?></b></label>
                            <select class="form-control" name="userGenderAdd">
                                <option value="1" <?php if (isset($_POST["userGenderAdd"]) && $_POST["userGenderAdd"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_genderOption1']; ?></option>
                                <option value="2" <?php if (isset($_POST["userGenderAdd"]) && $_POST["userGenderAdd"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_genderOption2']; ?></option>
                            </select required>
                            <!-- preferred language fields -->
                            <label for="userPreferredLanguageAdd"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_preferredLanguageLabel']; ?></b></label>
                            <select class="form-control" name="userPreferredLanguageAdd">
                                <option value="en" <?php if (isset($_POST["userPreferredLanguageAdd"]) && $_POST["userPreferredLanguageAdd"] == "en") { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_preferredLanguageOption1']; ?></option>
                                <option value="pt" <?php if (isset($_POST["userPreferredLanguageAdd"]) && $_POST["userPreferredLanguageAdd"] == "pt") { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_preferredLanguageOption2']; ?></option>
                            </select required>
                            <!-- access type fields -->
                            <label for="userAccessTypeAdd"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeLabel']; ?></b></label>
                            <select class="form-control" name="userAccessTypeAdd">
                                <option value="1" <?php if (isset($_POST["userAccessTypeAdd"]) && $_POST["userAccessTypeAdd"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeOption1']; ?>
                                <option value="2" <?php if (isset($_POST["userAccessTypeAdd"]) && $_POST["userAccessTypeAdd"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeOption2']; ?></option>
                            </select required>
                            * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                            <button type="submit" class="btn btn-success" name="addUser"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addUser_title']; ?></button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    </div>
    <div class="col">
        <form action="../settings/settings.php?users=1" method="post" class="d-flex">
            <input class="form-control me-2" type="text" name="userUsername" placeholder="<?php echo $translationsSettingsUsersSettings['settings_sidebar_form_searchUser_usernamePlaceholder']; ?>" required>
            <button class="btn btn-success" type="submit" name="userSearch"><?php echo $translationsSettingsUsersSettings['settings_users_settings_search']; ?></button>
            <?php if (isset($_POST["userSearch"])) { ?>
                                    <a class="ms-2 w-25 btn btn-primary" href="../settings/settings.php?users=1" role="button"><?php echo $translationsTemplateTop['template_top_global_button_listAll']; ?></a>
            <?php } ?>
        </form>
    </div>
</div>

<!-- users list zone -->
<?php if ($users != NULL && $users != -1 && $users != -2 && $users != -3) { ?>
    <!-- title zone -->
    <br>
    <p><?php echo $translationsSettingsUsersSettings['settings_users_settings_list_title1']; ?>                     <?php echo ($numUsers); ?>                     <?php echo $translationsSettingsUsersSettings['settings_users_settings_list_title2']; ?> (<?php echo $numRecords; ?>                     <?php echo $translationsSettingsUsersSettings['settings_users_settings_list_title3']; ?>:</p>
    <!-- list zone -->
    <ul class="list-group list-group-flush">
        <?php foreach ($users as $user) { ?>
            <li class="list-group-item d-flex justify-content-between">
                <div class="d-flex align-items-center">
                    <img src=<?php if (is_null($user["photo_path"])) {
                        if ($user["gender"] == 1) {
                            echo ("../img/avatar/male1.png");
                        } else {
                            echo ("../img/avatar/female1.png");
                        }
                    } else {
                        echo ($user["photo_path"]);
                    } ?> alt="userPicture" class="rounded-circle" width="55" height="55">
                    <div class="ms-3">
                        <div class="fw-bold">
                            <?php echo ($user["username"]); ?>
                        </div>
                        <b><?php echo $translationsSettingsUsersSettings['settings_users_settings_list_user_accesstype']; ?></b><?php if ($user["access_type"] == 1) {
                                echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeOption1'];
                            } else {
                                if ($user["access_type"] == 2) {
                                    echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeOption2'];
                                }
                            } ?>
                    </div>
                </div>
                <div>
                    <?php if ($user["is_active"] == 1) { ?>
                        <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle"><?php echo $translationsSettingsUsersSettings['settings_users_settings_list_isactive']; ?></span>
                    <?php } else { ?>
                        <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle"><?php echo $translationsSettingsUsersSettings['settings_users_settings_list_isinactive']; ?></span>
                    <?php } ?>

                    <!-- change user password button -->
                    <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editUserPasswordModal<?php echo ($user["id"]); ?>"><i class="fa-solid fa-key"></i></a>

                    <!-- change user password Modal -->
                    <div class="modal fade" id="editUserPasswordModal<?php echo ($user["id"]); ?>" tabindex="-1" aria-labelledby="editUserPasswordModal<?php echo ($user["id"]); ?>" aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="editUserPasswordModal<?php echo ($user["id"]); ?>"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_changeUserPassword_title']; ?></h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <form action="../settings/settings.php?userID=<?php echo ($user["id"]); ?>&editUserPasswordAdmin=1&users=1" method="post" enctype="multipart/form-data">
                                    <div class="modal-body">
                                        <!-- info banner to display password complexity requirements -->
                                        <div class="alert alert-info alert-dismissible d-flex align-items-center" role="alert">
                                            <!--<i class="fa-solid fa-circle-info me-1 allign-top"></i>-->
                                            <div>
                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_info_password_requirements']; ?>
                                                <br>
                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_info_password_requirements_characters']; ?>
                                                <br>
                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_info_password_requirements_capital_letters']; ?>
                                                <br>
                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_info_password_requirements_numbers']; ?>
                                                <br>
                                                <?php echo $translationsSettingsUsersSettings['settings_users_settings_info_password_requirements_special_characters']; ?>
                                            </div>
                                        </div>

                                        <p><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_changeUserPassword_body']; ?> <b><?php echo ($user["username"]); ?></b></p>

                                        <!-- password fields -->
                                        <label for="passUserEditAdmin"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_change_password_password']; ?></b></label>
                                        <input class="form-control" type="password" name="passUserEditAdmin" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_change_password_password']; ?>" value="<?php echo isset($_POST["passUserEditAdmin"]) ? $_POST["passUserEditAdmin"] : ''; ?>" required>

                                        <!-- repeat password fields -->
                                        <label class="mt-1" for="passRepeatUserEditAdmin"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_change_password_repeat_password']; ?></b></label>
                                        <input class="form-control" type="password" name="passRepeatUserEditAdmin" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_change_password_repeat_password']; ?>" value="<?php echo isset($_POST["passRepeatUserEditAdmin"]) ? $_POST["passRepeatUserEditAdmin"] : ''; ?>" required>

                                        <p class="mt-1">* <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?></p>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>

                                        <button type="submit" class="btn btn-success" name="editUserPasswordAdmin"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_changeUserPassword_title']; ?></button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>

                    <!-- edit user button -->
                    <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editUserModal<?php echo ($user["id"]); ?>"><i class="fa-solid fa-pen-to-square"></i></a>

                    <!-- Modal edit user -->
                    <div class="modal fade" id="editUserModal<?php echo ($user["id"]); ?>" tabindex="-1" aria-labelledby="editUserModal<?php echo ($user["id"]); ?>" aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="editUserModal<?php echo ($user["id"]); ?>"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_editUser_title']; ?></h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <form action="../settings/settings.php?userID=<?php echo ($user["id"]); ?>&editUser=1&users=1" method="post" enctype="multipart/form-data">
                                    <div class="modal-body">
                                        <label for="userImgEdit"><b><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_photoLabel']; ?></b></label>
                                        <div>
                                            <div class="row">
                                                <div class="col">
                                                    <input class="form-control" type="file" accept="image/*" name="userImgEdit" id="userImgEdit" value="<?php echo ($user["photo_path"]); ?>">
                                                </div>
                                                <?php if (!is_null($user["photo_path"])) { ?>
                                                    <div class="col">
                                                        <a class="w-100 btn btn-danger" href="../settings/settings.php?userID=<?php echo ($user["id"]); ?>&deletePhotoUser=1&users=1" role="button"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_editUser_deleteUserPhoto']; ?></a>
                                                    </div>
                                                <?php } ?>
                                            </div>
                                        </div>
                                        <!-- username fields -->
                                        <label for="userUsernameEdit"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_usernameLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userUsernameEdit" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_usernamePlaceholder']; ?>" maxlength="250" value="<?php echo ($user["username"]); ?>" required>
                                        <!-- name fields -->
                                        <label for="userNameEdit"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_nameLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userNameEdit" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_namePlaceholder']; ?>" maxlength="250" value="<?php echo ($user["name"]); ?>" required>
                                        <!-- email fields -->
                                        <label for="userEmailEdit"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_emailLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userEmailEdit" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_emailPlaceholder']; ?>" maxlength="45" value="<?php echo ($user["email"]); ?>" required>
                                        <!-- city fields -->
                                        <label for="userCityEdit"><b><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_cityLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userCityEdit" placeholder="<?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_cityPlaceholder']; ?>" maxlength="45" value="<?php echo ($user["city"]); ?>">
                                        <!-- birth date fields -->
                                        <label for="userBirthDateEdit"><b><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_birthdateLabel']; ?></b></label>
                                        <input class="form-control" type="date" name="userBirthDateEdit" value="<?php echo ($user["birthdate"]); ?>">
                                        <!-- gender fields -->
                                        <label for="userGenderEdit"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_genderLabel']; ?></b></label>
                                        <select class="form-control" name="userGenderEdit">
                                            <option value="1" <?php if ($user["gender"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_genderOption1']; ?></option>
                                            <option value="2" <?php if ($user["gender"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_genderOption2']; ?></option>
                                        </select required>
                                        <!-- preferred language fields -->
                                        <label for="userPreferredLanguageEdit"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_preferredLanguageLabel']; ?></b></label>
                                        <select class="form-control" name="userPreferredLanguageEdit">
                                            <option value="en" <?php if ($user["preferred_language"] == "en") { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_preferredLanguageOption1']; ?></option>
                                            <option value="pt" <?php if ($user["preferred_language"] == "pt") { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_preferredLanguageOption2']; ?></option>
                                        </select required>
                                        <!-- access type fields -->
                                        <label for="userTypeEdit"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeLabel']; ?></b></label>
                                        <select class="form-control" name="userTypeEdit">
                                            <option value="1" <?php if ($user["access_type"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeOption1']; ?></option>
                                            <option value="2" <?php if ($user["access_type"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_typeOption2']; ?></option>
                                        </select required>
                                        <!-- user is_active fields -->
                                        <label for="userIsActiveEdit"><b>* <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_isActiveLabel']; ?></b></label>
                                        <select class="form-control" name="userIsActiveEdit">
                                            <option value="1" <?php if ($user["is_active"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_isActiveOption1']; ?></option>
                                            <option value="2" <?php if ($user["is_active"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_addEditUser_isActiveOption2']; ?></option>
                                        </select required>
                                        * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                        <button type="submit" class="btn btn-success" name="userEdit"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_editUser_title']; ?></button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>

                    <?php if ($user["id"] != $_SESSION["id"]) { ?>
                        <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteUserModal<?php echo ($user["id"]); ?>"><i class="fa-solid fa-trash-can"></i></a>
                    <?php } ?>

                    <!-- Modal -->
                    <div class="modal fade" id="deleteUserModal<?php echo ($user["id"]); ?>" tabindex="-1" aria-labelledby="deleteUserModal<?php echo ($user["id"]); ?>" aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="deleteUserModal<?php echo ($user["id"]); ?>"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_deleteUser_title']; ?></h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <div class="modal-body">
                                    <?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_deleteUser_body']; ?> <b><?php echo ($user["username"]); ?></b>?
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                    <a type="button" class="btn btn-danger" href="../settings/settings.php?userID=<?php echo ($user["id"]); ?>&deleteUser=1&users=1"><?php echo $translationsSettingsUsersSettings['settings_users_settings_modal_deleteUser_title']; ?></a>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </li>
        <?php } ?>
    </ul>
    <?php if (!isset($_POST["userSearch"])) { ?>
        <br>
        <nav>
            <ul class="pagination justify-content-center">
                <li class="page-item <?php if ($pageNumberUsers == 1) {
                    echo "disabled";
                } ?>"><a class="page-link" href="?pageNumberUsers=1">«</a></li>
                <?php for ($i = 1; $i <= $total_pages; $i++) { ?>
                                        <li class="page-item <?php if ($i == $pageNumberUsers) {
                                            echo "active";
                                        } ?>"><a class="page-link" href="?pageNumberUsers=<?php echo ($i); ?>"><?php echo ($i); ?></a></li>
                <?php } ?>
                <li class="page-item <?php if ($pageNumberUsers == $total_pages) {
                    echo "disabled";
                } ?>"><a class="page-link" href="?pageNumberUsers=<?php echo ($total_pages); ?>">»</a></li>
            </ul>
        </nav>
    <?php } ?>
<?php } ?>