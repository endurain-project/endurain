<?php
if (!isset($_SESSION)) {
    session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "settings";
// users
$numUsers = 0;
$users = [];
$addUserAction = -9000;
$photoDeleted = -9000;
$deleteAction = -9000;
$deletePhotoUserAction = -9000;
$editUserAction = -9000;
$pageNumberUsers = 1;
// profile
$editProfileAction = -9000;
$deletePhotoProfileAction = -9000;
// gear
$numGears = 0;
$gears = [];
$pageNumberGears = 1;
$addGearAction = -9000;
$editGearAction = -9000;
$deleteGearAction = -9000;

// general
$numRecords = 5;

if (!isLogged()) {
    header("Location: ../login.php");
}

if (!isTokenValid($_SESSION["token"])) {
    header("Location: ../logout.php?sessionExpired=1");
}

if ($_SESSION["access_type"] != 2) {
    $_GET["profileSettings"] = 1;
}

// Load the language file based on the user's preferred language
switch ($_SESSION["preferred_language"]) {
    case 'en':
        $translationsSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/en.php';
        break;
    case 'pt':
        $translationsSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/pt.php';
        break;
        // ...
    default:
        $translationsSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/en.php';
}

# Users section
/* Add user action */
if (isset($_POST["addUser"]) && $_GET["addUser"] == 1) {
    if (empty(trim($_POST["UserNameAdd"]))) {
        $_POST["UserNameAdd"] = NULL;
    }

    if (isset($_FILES["userImgAdd"]) && $_FILES["userImgAdd"]["error"] == 0) {
        $target_dir = "../img/users_img/";
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
        $userImg = getUserPhotoFromID($_GET["userID"]);
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
                if (unlink(getUserPhotoAuxFromID($_GET["userID"])[0])) {
                    unsetUserPhoto($_GET["userID"]);
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
            $userPhoto = getUserPhotoFromID($_GET["userID"])[0];
            if (empty($userPhoto)) {
                $userPhoto = NULL;
            }
            $userPhotoAux = getUserPhotoAuxFromID($_GET["userID"])[0];
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
    if (unlink(getUserPhotoAuxFromID($_GET["userID"])[0])) {
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
            if (!is_null($photo_path[0])) {
                if (unlink($photo_path[0])) {
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
    $users = getUserFromUsername(urlencode(trim($_POST["userUsername"])));
    if ($users == NULL) {
        $numUsers = 0;
    } else {
        $numUsers = 1;
    }
}

// User profile section
/* Edit action */
if (isset($_POST["editProfile"])) {
    if (empty(trim($_POST["profileNameEdit"]))) {
        $_POST["profileNameEdit"] = NULL;
    }

    if (isset($_FILES["profileImgEdit"]) && $_FILES["profileImgEdit"]["error"] == 0) {
        $target_dir = "../img/users_img/";
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
            if (unlink(getUserPhotoAuxFromID($_SESSION["id"])[0])) {
                unsetUserPhoto($_SESSION["id"]);
            }
            if (move_uploaded_file($_FILES["profileImgEdit"]["tmp_name"], $target_file)) {
                $photoPath = "..\img\users_img\\" . $newname;
                $photoPath_aux = $target_file;
                $editProfileAction = editUser(trim($_POST["profileNameEdit"]), trim($_POST["profileUsernameEdit"]), trim($_POST["profileEmailEdit"]), $_SESSION["id"], $_POST["profilePreferredLanguageEdit"], trim($_POST["profileCityEdit"]), $_POST["profileBirthDateEdit"], $_POST["profileGenderEdit"], $_SESSION["access_type"], $photoPath, $photoPath_aux, 1);
                setUserRelatedInfoSession($_SESSION["token"]);
            } else {
                $editProfileAction = -5;
                $uploadOk = 0;
            }
        }
    } else {
        $profilePhoto = getUserPhotoFromID($_SESSION["id"])[0];
        $profilePhotoAux = getUserPhotoAuxFromID($_SESSION["id"]);
        $editProfileAction = editUser(trim($_POST["profileNameEdit"]), trim($_POST["profileUsernameEdit"]), trim($_POST["profileEmailEdit"]), $_SESSION["id"], $_POST["profilePreferredLanguageEdit"], trim($_POST["profileCityEdit"]), $_POST["profileBirthDateEdit"], $_POST["profileGenderEdit"], $_SESSION["access_type"], $profilePhoto, $profilePhotoAux, 1);
        setUserRelatedInfoSession($_SESSION["token"]);
    }
}

/* Delete user photo */
if (isset($_GET["deleteProfilePhoto"]) && $_GET["deleteProfilePhoto"] == 1) {
    if (unlink(getUserPhotoAuxFromID($_SESSION["id"])[0])) {
        $deletePhotoProfileAction = unsetUserPhoto($_SESSION["id"]);
        if ($deletePhotoProfileAction == 0) {
            $_SESSION["photo_path"] = NULL;
            $_SESSION["photo_path_aux"] = NULL;
        }
    } else {
        $deletePhotoProfileAction = -3;
    }
}

if (isset($_GET["linkStrava"]) && $_GET["linkStrava"] == 1) {
    $state = bin2hex(random_bytes(16));
    $generate_user_state = setUniqueUserStateStravaLink($state);
    if ($generate_user_state == 0) {
        // Example PHP code for the authentication link
        $linkStrava = linkStrava($state);
    }
    #$unset_user_state = unsetUniqueUserStateStravaLink();
}

if (isset($_GET["stravaLinked"]) && $_GET["stravaLinked"] == 1) {
    setUserRelatedInfoSession($_SESSION["token"]);
    $unset_user_state = unsetUniqueUserStateStravaLink();
    #getStravaActivities();
}

// Gear section
/* Add action */
if (isset($_POST["addGear"]) && $_GET["addGear"] == 1) {
    if (empty(trim($_POST["gearBrandAdd"]))) {
        $_POST["gearBrandAdd"] = NULL;
    }
    if (empty(trim($_POST["gearModelAdd"]))) {
        $_POST["gearModelAdd"] = NULL;
    }

    $addGearAction = newGear(urlencode(trim($_POST["gearBrandAdd"])), urlencode(trim($_POST["gearModelAdd"])), urlencode(trim($_POST["gearNicknameAdd"])), $_POST["gearTypeAdd"], $_POST["gearDateAdd"]);
}

/* Edit action */
if (isset($_POST["editGear"]) && $_GET["editGear"] == 1) {
    if (empty(trim($_POST["gearBrandEdit"]))) {
        $_POST["gearBrandEdit"] = NULL;
    }
    if (empty(trim($_POST["gearModelEdit"]))) {
        $_POST["gearModelEdit"] = NULL;
    }
    $editGearAction = editGear($_GET["gearID"], urlencode(trim($_POST["gearBrandEdit"])), urlencode(trim($_POST["gearModelEdit"])), urlencode(trim($_POST["gearNicknameEdit"])), $_POST["gearTypeEdit"], date("Y-m-d H:i:s", strtotime($_POST["gearDateEdit"] . " 00:00:00")), $_POST["gearIsActiveEdit"]);
}

/* Delete gear */
if (isset($_GET["deleteGear"]) && $_GET["deleteGear"] == 1) {
    $deleteGearAction = deleteGear($_GET["gearID"]);
}

if (isset($_GET["pageNumberGears"])) {
    $pageNumberGears = $_GET["pageNumberGears"];
}

if (!isset($_POST["gearSearch"])) {
    $gears = getGearPagination($pageNumberGears, $numRecords);
    $numGears = numGears();
    $total_pages = ceil($numGears / $numRecords);
} else {
    $gears = getGearFromNickname(urlencode(trim($_POST["gearNickname"])));
    if ($gears == NULL) {
        $numGears = 0;
    } else {
        $numGears = 1;
    }
}
?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<div class="container mt-4">
    <h1><?php echo $translationsSettings['settings_title']; ?></h1>
</div>

<div class="container mt-4">
    <!-- Error banners -->

    <!-- Info banners -->

    <!-- Success banners -->

    <div class="row row-gap-3">
        <!-- sidebar zone -->
        <div class="col-lg-4 col-md-12">
            <ul class="nav nav-pills flex-column mb-auto" id="sidebarNav">
                <?php if ($_SESSION["access_type"] == 2) { ?>
                    <li class="nav-item">
                        <a href="#" class="nav-link <?php if (!isset($_GET["profileSettings"]) && !isset($_GET["global"]) && !isset($_GET["gearSettings"]) && $_SESSION["access_type"] == 2) {
                                                        echo "text-white active";
                                                    } ?>" onclick="changeActive(event, 'divUsers')">
                            <svg class="bi pe-none me-2" width="16" height="16"></svg>
                            <?php echo $translationsSettings['settings_sidebar_users']; ?>
                        </a>
                    </li>
                    <li class="nav-item">
                        <a href="#" class="nav-link <?php if (isset($_GET["global"]) && $_SESSION["access_type"] == 2) {
                                                        echo "text-white active";
                                                    } ?>" onclick="changeActive(event, 'divGlobal')">
                            <svg class="bi pe-none me-2" width="16" height="16"></svg>
                            <?php echo $translationsSettings['settings_sidebar_global']; ?>
                        </a>
                    </li>
                    <hr>
                <?php } ?>
                <li class="nav-item">
                    <a href="#" class="nav-link <?php if (isset($_GET["profileSettings"]) || ($_SESSION["access_type"] == 1 && !isset($_GET["profileSettings"]) && !isset($_GET["gearSettings"]))) {
                                                    echo "text-white active";
                                                } ?>" onclick="changeActive(event, 'divProfileSettings')">
                        <svg class="bi pe-none me-2" width="16" height="16"></svg>
                        <?php echo $translationsSettings['settings_sidebar_profileSettings']; ?>
                    </a>
                </li>
                <li class="nav-item">
                    <a href="#" class="nav-link <?php if (isset($_GET["gearSettings"])) {
                                                    echo "text-white active";
                                                } ?>" onclick="changeActive(event, 'divGearSettings')">
                        <svg class="bi pe-none me-2" width="16" height="16"></svg>
                        <?php echo $translationsSettings['settings_sidebar_gearSettings']; ?>
                    </a>
                </li>
            </ul>
        </div>
        <hr class="d-lg-none">


        <!-- users zone -->
        <div class="col" id="divUsers" style="display: <?php if (isset($_GET["global"]) || isset($_GET["profileSettings"]) || isset($_GET["gearSettings"])) {
                                                            echo "none";
                                                        } else {
                                                            echo "block";
                                                        } ?>;">
            <!-- Error banners -->
            <?php if ($users == -1 || $users == -2 || $editUserAction == -1 || $editUserAction == -2 || $editUserAction == -3 || $editUserAction == -4 || $editUserAction == -5 || $editUserAction == -6 || $deleteAction == -1 || $deleteAction == -2 || $deleteAction == -409 || $deleteAction == -3 || $addUserAction == -1 || $addUserAction == -2 || $addUserAction == -3 || $addUserAction == -4 || $addUserAction == -5 || $addUserAction == -6 || $deletePhotoUserAction == -1 || $deletePhotoUserAction == -2 || $deletePhotoUserAction == -3) { ?>
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
                                    <?php echo $translationsSettings['settings_sidebar_users_error_editUser_-3']; ?> (-3).
                                <?php } else { ?>
                                    <?php if ($editUserAction == -4) { ?>
                                        <?php echo $translationsSettings['settings_sidebar_users_error_addEditUser_-4']; ?> (-4).
                                    <?php } else { ?>
                                        <?php if ($editUserAction == -5) { ?>
                                            <?php echo $translationsSettings['settings_sidebar_users_error_addEditUser_-5']; ?> (-5).
                                        <?php } else { ?>
                                            <?php if ($editUserAction == -6) { ?>
                                                <?php echo $translationsSettings['settings_sidebar_users_error_addEditUser_-6']; ?> (-6).
                                            <?php } else { ?>
                                                <?php if ($deleteAction == -3) { ?>
                                                    <?php echo $translationsSettings['settings_sidebar_users_error_deleteUser_-3']; ?> (-3).
                                                <?php } else { ?>
                                                    <?php if ($deleteAction == -409) { ?>
                                                        <?php echo $translationsSettings['settings_sidebar_users_error_deleteUser_-409']; ?> (-3).
                                                    <?php } else { ?>
                                                        <?php if ($addUserAction == -3) { ?>
                                                            <?php echo $translationsSettings['settings_sidebar_users_error_addUser_-3']; ?> (-3).
                                                        <?php } else { ?>
                                                            <?php if ($addUserAction == -4) { ?>
                                                                <?php echo $translationsSettings['settings_sidebar_users_error_addEditUser_-4']; ?> (-4).
                                                            <?php } else { ?>
                                                                <?php if ($addUserAction == -5) { ?>
                                                                    <?php echo $translationsSettings['settings_sidebar_users_error_addEditUser_-5']; ?> (-5).
                                                                <?php } else { ?>
                                                                    <?php if ($addUserAction == -6) { ?>
                                                                        <?php echo $translationsSettings['settings_sidebar_users_error_addEditUser_-6']; ?> (-6).
                                                                    <?php } else { ?>
                                                                        <?php if ($deletePhotoUserAction == -3) { ?>
                                                                            <?php echo $translationsSettings['settings_sidebar_users_error_deleteUserPhoto_-3']; ?> (-3).
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
                            <?php echo $translationsSettings['settings_sidebar_users_error_searchUser_NULL']; ?> (NULL).
                        <?php } else { ?>
                            <?php if ($deleteAction == 0 && $photoDeleted == 1) { ?>
                                <?php echo $translationsSettings['settings_sidebar_users_info_userDeleted_photoNotDeleted']; ?>
                            <?php } ?>
                        <?php } ?>
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                </div>
            <?php } ?>

            <!-- Success banners -->
            <?php if ($addUserAction == 0 || $editUserAction == 0 || ($deleteAction == 0 && $photoDeleted == 0) || ($deleteAction == 0 && $photoDeleted == 2) || $deletePhotoUserAction == 0) { ?>
                <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
                    <div>
                        <i class="fa-regular fa-circle-check me-1"></i>
                        <?php if ($addUserAction == 0) { ?>
                            <?php echo $translationsSettings['settings_sidebar_users_success_userAdded']; ?>
                        <?php } else { ?>
                            <?php if ($editUserAction == 0) { ?>
                                <?php echo $translationsSettings['settings_sidebar_users_success_userEdited']; ?>
                            <?php } else { ?>
                                <?php if (($deleteAction == 0 && $photoDeleted == 0) || ($deleteAction == 0 && $photoDeleted == 2)) { ?>
                                    <?php echo $translationsSettings['settings_sidebar_users_success_userDeleted']; ?>
                                <?php } else { ?>
                                    <?php if ($deletePhotoUserAction == 0) { ?>
                                        <?php echo $translationsSettings['settings_sidebar_users_success_userPhotoDeleted']; ?>
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
                    <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addUserModal"><?php echo $translationsSettings['settings_sidebar_button_addUser']; ?></a>

                    <!-- Modal add user -->
                    <div class="modal fade" id="addUserModal" tabindex="-1" aria-labelledby="addUserModal" aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="addUserModal"><?php echo $translationsSettings['settings_sidebar_users_modal_addUser_title']; ?></h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <form action="../settings/settings.php?addUser=1&users=1" method="post" enctype="multipart/form-data">
                                    <div class="modal-body">
                                        <!-- img fields -->
                                        <label for="userImgAdd"><b><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_photoLabel']; ?></b></label>
                                        <input class="form-control" type="file" accept="image/*" name="userImgAdd" id="userImgAdd" value="<?php echo ($_POST["userImgAdd"]); ?>">
                                        <!-- username fields -->
                                        <label for="userUsernameAdd"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_usernameLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userUsernameAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_usernamePlaceholder']; ?>" maxlength="45" value="<?php echo ($_POST["userUsernameAdd"]); ?>" required>
                                        <!-- name fields -->
                                        <label for="userNameAdd"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_nameLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userNameAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_namePlaceholder']; ?>" maxlength="45" value="<?php echo ($_POST["userNameAdd"]); ?>" required>
                                        <!-- email fields -->
                                        <label for="userEmailAdd"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_emailLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userEmailAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_emailPlaceholder']; ?>" maxlength="45" value="<?php echo ($_POST["userEmailAdd"]); ?>" required>
                                        <!-- password fields -->
                                        <label for="passUserAdd"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_passwordLabel']; ?></b></label>
                                        <input class="form-control" type="password" name="passUserAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_passwordPlaceholder']; ?>" value="<?php echo ($_POST["passUserAdd"]); ?>" required>
                                        <!-- city fields -->
                                        <label for="userCityAdd"><b><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_cityLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="userCityAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_cityPlaceholder']; ?>" maxlength="45" value="<?php echo ($_POST["userCityAdd"]); ?>">
                                        <!-- birth date fields -->
                                        <label for="userBirthDateAdd"><b><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_birthdateLabel']; ?></b></label>
                                        <input class="form-control" type="date" name="userBirthDateAdd" value="<?php echo ($_POST["userBirthDateAdd"]); ?>">
                                        <!-- gender fields -->
                                        <label for="userGenderAdd"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_genderLabel']; ?></b></label>
                                        <select class="form-control" name="userGenderAdd">
                                            <option value="1" <?php if ($_POST["userGenderAdd"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_genderOption1']; ?></option>
                                            <option value="2" <?php if ($_POST["userGenderAdd"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_genderOption2']; ?></option>
                                        </select required>
                                        <!-- preferred language fields -->
                                        <label for="userPreferredLanguageAdd"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_preferredLanguageLabel']; ?></b></label>
                                        <select class="form-control" name="userPreferredLanguageAdd">
                                            <option value="en" <?php if ($_POST["userPreferredLanguageAdd"] == "en") { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_preferredLanguageOption1']; ?></option>
                                            <option value="pt" <?php if ($_POST["userPreferredLanguageAdd"] == "pt") { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_preferredLanguageOption2']; ?></option>
                                        </select required>
                                        <!-- access type fields -->
                                        <label for="userAccessTypeAdd"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeLabel']; ?></b></label>
                                        <select class="form-control" name="userAccessTypeAdd">
                                            <option value="1" <?php if ($_POST["userAccessTypeAdd"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeOption1']; ?>
                                            <option value="2" <?php if ($_POST["userAccessTypeAdd"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeOption2']; ?></option>
                                        </select required>
                                        * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                        <button type="submit" class="btn btn-success" name="addUser"><?php echo $translationsSettings['settings_sidebar_users_modal_addUser_title']; ?></button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <form action="../settings/settings.php?users=1" method="post" class="d-flex">
                        <input class="form-control me-2" type="text" name="userUsername" placeholder="<?php echo $translationsSettings['settings_sidebar_form_searchUser_usernamePlaceholder']; ?>" required>
                        <button class="btn btn-success" type="submit" name="userSearch"><?php echo $translationsSettings['settings_sidebar_form_searchSpaceRoomUser_namePlaceholder']; ?></button>
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
                <p><?php echo $translationsSettings['settings_sidebar_users_list_title1']; ?> <?php echo ($numUsers); ?> <?php echo $translationsSettings['settings_sidebar_users_list_title2']; ?> (<?php echo $numRecords; ?> <?php echo $translationsSettings['settings_sidebar_users_list_title3']; ?>:</p>
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
                                    <b><?php echo $translationsSettings['settings_sidebar_users_list_user_accesstype']; ?></b><?php if ($user["access_type"] == 1) {
                                                                                                                                    echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeOption1'];
                                                                                                                                } else {
                                                                                                                                    if ($user["access_type"] == 2) {
                                                                                                                                        echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeOption2'];
                                                                                                                                    }
                                                                                                                                } ?>
                                </div>
                            </div>
                            <div>
                                <?php if ($user["is_active"] == 1) { ?>
                                    <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle"><?php echo $translationsSettings['settings_sidebar_users_list_isactive']; ?></span>
                                <?php } else { ?>
                                    <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle"><?php echo $translationsSettings['settings_sidebar_users_list_isinactive']; ?></span>
                                <?php } ?>

                                <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editUserModal<?php echo ($user["id"]); ?>"><i class="fa-solid fa-pen-to-square"></i></a>

                                <!-- Modal edit user -->
                                <div class="modal fade" id="editUserModal<?php echo ($user["id"]); ?>" tabindex="-1" aria-labelledby="editUserModal<?php echo ($user["id"]); ?>" aria-hidden="true">
                                    <div class="modal-dialog">
                                        <div class="modal-content">
                                            <div class="modal-header">
                                                <h1 class="modal-title fs-5" id="editUserModal<?php echo ($user["id"]); ?>"><?php echo $translationsSettings['settings_sidebar_users_modal_editUser_title']; ?></h1>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                            </div>
                                            <form action="../settings/settings.php?userID=<?php echo ($user["id"]); ?>&editUser=1&users=1" method="post" enctype="multipart/form-data">
                                                <div class="modal-body">
                                                    <label for="userImgEdit"><b><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_photoLabel']; ?></b></label>
                                                    <div>
                                                        <div class="row">
                                                            <div class="col">
                                                                <input class="form-control" type="file" accept="image/*" name="userImgEdit" id="userImgEdit" value="<?php echo ($user["photo_path"]); ?>">
                                                            </div>
                                                            <?php if (!is_null($user["photo_path"])) { ?>
                                                                <div class="col">
                                                                    <a class="w-100 btn btn-danger" href="../settings/settings.php?userID=<?php echo ($user["id"]); ?>&deletePhotoUser=1&users=1" role="button"><?php echo $translationsSettings['settings_sidebar_users_modal_editUser_deleteUserPhoto']; ?></a>
                                                                </div>
                                                            <?php } ?>
                                                        </div>
                                                    </div>
                                                    <!-- username fields -->
                                                    <label for="userUsernameEdit"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_usernameLabel']; ?></b></label>
                                                    <input class="form-control" type="text" name="userUsernameEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_usernamePlaceholder']; ?>" maxlength="250" value="<?php echo ($user["username"]); ?>" required>
                                                    <!-- name fields -->
                                                    <label for="userNameEdit"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_nameLabel']; ?></b></label>
                                                    <input class="form-control" type="text" name="userNameEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_namePlaceholder']; ?>" maxlength="250" value="<?php echo ($user["name"]); ?>" required>
                                                    <!-- email fields -->
                                                    <label for="userEmailEdit"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_emailLabel']; ?></b></label>
                                                    <input class="form-control" type="text" name="userEmailEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_emailPlaceholder']; ?>" maxlength="45" value="<?php echo ($user["email"]); ?>" required>
                                                    <!-- city fields -->
                                                    <label for="userCityEdit"><b><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_cityLabel']; ?></b></label>
                                                    <input class="form-control" type="text" name="userCityEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_cityPlaceholder']; ?>" maxlength="45" value="<?php echo ($user["city"]); ?>">
                                                    <!-- birth date fields -->
                                                    <label for="userBirthDateEdit"><b><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_birthdateLabel']; ?></b></label>
                                                    <input class="form-control" type="date" name="userBirthDateEdit" value="<?php echo ($user["birthdate"]); ?>">
                                                    <!-- gender fields -->
                                                    <label for="userGenderEdit"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_genderLabel']; ?></b></label>
                                                    <select class="form-control" name="userGenderEdit">
                                                        <option value="1" <?php if ($user["gender"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_genderOption1']; ?></option>
                                                        <option value="2" <?php if ($user["gender"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_genderOption2']; ?></option>
                                                    </select required>
                                                    <!-- preferred language fields -->
                                                    <label for="userPreferredLanguageEdit"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_preferredLanguageLabel']; ?></b></label>
                                                    <select class="form-control" name="userPreferredLanguageEdit">
                                                        <option value="en" <?php if ($user["preferred_language"] == "en") { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_preferredLanguageOption1']; ?></option>
                                                        <option value="pt" <?php if ($user["preferred_language"] == "pt") { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_preferredLanguageOption2']; ?></option>
                                                    </select required>
                                                    <!-- access type fields -->
                                                    <label for="userTypeEdit"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeLabel']; ?></b></label>
                                                    <select class="form-control" name="userTypeEdit">
                                                        <option value="1" <?php if ($user["access_type"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeOption1']; ?></option>
                                                        <option value="2" <?php if ($user["access_type"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_typeOption2']; ?></option>
                                                    </select required>
                                                    <!-- user is_active fields -->
                                                    <label for="userIsActiveEdit"><b>* <?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_isActiveLabel']; ?></b></label>
                                                    <select class="form-control" name="userIsActiveEdit">
                                                        <option value="1" <?php if ($user["is_active"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_isActiveOption1']; ?></option>
                                                        <option value="2" <?php if ($user["is_active"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_users_modal_addEditUser_isActiveOption2']; ?></option>
                                                    </select required>
                                                    * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                                </div>
                                                <div class="modal-footer">
                                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                                    <button type="submit" class="btn btn-success" name="userEdit"><?php echo $translationsSettings['settings_sidebar_users_modal_editUser_title']; ?></button>
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
                                                <h1 class="modal-title fs-5" id="deleteUserModal<?php echo ($user["id"]); ?>"><?php echo $translationsSettings['settings_sidebar_users_modal_deleteUser_title']; ?></h1>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                            </div>
                                            <div class="modal-body">
                                                <?php echo $translationsSettings['settings_sidebar_users_modal_deleteUser_body']; ?> <b><?php echo ($user["username"]); ?></b>?
                                            </div>
                                            <div class="modal-footer">
                                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                                <a type="button" class="btn btn-danger" href="../settings/settings.php?userID=<?php echo ($user["id"]); ?>&deleteUser=1&users=1"><?php echo $translationsSettings['settings_sidebar_users_modal_deleteUser_title']; ?></a>
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
        </div>

        <!-- global zone -->
        <div class="col" id="divGlobal" style="display: <?php if (isset($_GET["global"])) {
                                                            echo "block";
                                                        } else {
                                                            echo "none";
                                                        } ?>;">

        </div>

        <!-- user settings zone -->
        <div class="col" id="divProfileSettings" style="display: <?php if (isset($_GET["profileSettings"])) {
                                                                        echo "block";
                                                                    } else {
                                                                        echo "none";
                                                                    } ?>;">
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
                                    <?php echo $translationsSettings['settings_sidebar_profile_error_deleteProfilePhoto_-3']; ?> (-3).
                                <?php } else { ?>
                                    <?php if ($editProfileAction == -3) { ?>
                                        <?php echo $translationsSettings['settings_sidebar_spaces_error_addEditSpace_-3']; ?> (-3).
                                    <?php } else { ?>
                                        <?php if ($editProfileAction == -4) { ?>
                                            <?php echo $translationsSettings['settings_sidebar_spaces_error_addEditSpace_-4']; ?> (-4).
                                        <?php } else { ?>
                                            <?php if ($editProfileAction == -5) { ?>
                                                <?php echo $translationsSettings['settings_sidebar_spaces_error_addEditSpace_-5']; ?> (-5).
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
                            <?php echo $translationsSettings['settings_sidebar_profile_success_profilePhotoDeleted']; ?>
                        <?php } else { ?>
                            <?php if ($editProfileAction == 0) { ?>
                                <?php echo $translationsSettings['settings_sidebar_profile_success_profileEdited']; ?>
                            <?php } else { ?>
                                <?php if (isset($_GET["stravaLinked"]) && $_GET["stravaLinked"] == 1) { ?>
                                    <?php echo $translationsSettings['settings_sidebar_profile_success_stravaLinked']; ?>
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
                        <a class="mt-4 w-100 btn btn-danger" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteProfilePhotoModal"><?php echo $translationsSettings['settings_sidebar_profile_deleteProfilePhoto']; ?></a>
                    <?php } ?>

                    <!-- Modal delete profile photo -->
                    <div class="modal fade" id="deleteProfilePhotoModal" tabindex="-1" aria-labelledby="deleteProfilePhotoModal" aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="deleteProfilePhotoModal"><?php echo $translationsSettings['settings_sidebar_profile_modal_title_deleteProfilePhoto']; ?></h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <div class="modal-body">
                                    <?php echo $translationsSettings['settings_sidebar_profile_modal_body_deleteProfilePhoto']; ?>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                    <a type="button" class="btn btn-danger" href="../settings/settings.php?deleteProfilePhoto=1&profileSettings=1"><?php echo $translationsSettings['settings_sidebar_profile_modal_title_deleteProfilePhoto']; ?></a>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Edit profile section -->
                    <a class="mt-2 w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editProfileModal<?php echo ($_SESSION["id"]); ?>"><?php echo $translationsSettings['settings_sidebar_profile_button_editprofile']; ?></a>

                    <!-- Modal edit profile -->
                    <div class="modal fade" id="editProfileModal<?php echo ($_SESSION["id"]); ?>" tabindex="-1" aria-labelledby="editProfileModal<?php echo ($_SESSION["id"]); ?>" aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="editProfileModal<?php echo ($_SESSION["id"]); ?>"><?php echo $translationsSettings['settings_sidebar_profile_editProfile_title']; ?></h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <form action="../settings/settings.php?editProfile=1&profileSettings=1" method="post" enctype="multipart/form-data">
                                    <div class="modal-body">
                                        <label for="profileImgEdit"><b><?php echo $translationsSettings['settings_sidebar_profile_photo_label']; ?></b></label>
                                        <div>
                                            <div class="row">
                                                <div class="col">
                                                    <input class="form-control" type="file" accept="image/*" name="profileImgEdit" id="profileImgEdit" value="<?php echo ($_SESSION["photo_path"]); ?>">
                                                </div>
                                            </div>
                                        </div>
                                        <!-- username fields -->
                                        <label for="profileUsernameEdit"><b>* <?php echo $translationsSettings['settings_sidebar_profile_username_label']; ?></b></label>
                                        <input class="form-control" type="text" name="profileUsernameEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_profile_username_placeholder']; ?>" maxlength="250" value="<?php echo ($_SESSION["username"]); ?>" required>
                                        <!-- name fields -->
                                        <label for="profileNameEdit"><b>* <?php echo $translationsSettings['settings_sidebar_profile_name_label']; ?></b></label>
                                        <input class="form-control" type="text" name="profileNameEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_profile_name_placeholder']; ?>" maxlength="250" value="<?php echo ($_SESSION["name"]); ?>" required>
                                        <!-- email fields -->
                                        <label for="profileEmailEdit"><b>* <?php echo $translationsSettings['settings_sidebar_profile_email_label']; ?></b></label>
                                        <input class="form-control" type="text" name="profileEmailEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_profile_email_placeholder']; ?>" maxlength="45" value="<?php echo ($_SESSION["email"]); ?>" required>
                                        <!-- city fields -->
                                        <label for="profileCityEdit"><b><?php echo $translationsSettings['settings_sidebar_profile_city_label']; ?></b></label>
                                        <input class="form-control" type="text" name="profileCityEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_profile_city_placeholder']; ?>" maxlength="45" value="<?php echo ($_SESSION["city"]); ?>">
                                        <!-- birth date fields -->
                                        <label for="profileBirthDateEdit"><b><?php echo $translationsSettings['settings_sidebar_profile_birthdate_label']; ?></b></label>
                                        <input class="form-control" type="date" name="profileBirthDateEdit" value="<?php echo ($_SESSION["birthdate"]); ?>">
                                        <!-- gender fields -->
                                        <label for="profileGenderEdit"><b>* <?php echo $translationsSettings['settings_sidebar_profile_gender_label']; ?></b></label>
                                        <select class="form-control" name="profileGenderEdit">
                                            <option value="1" <?php if ($_SESSION["gender"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_profile_gender_option1']; ?></option>
                                            <option value="2" <?php if ($_SESSION["gender"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_profile_gender_option2']; ?></option>
                                        </select required>
                                        <!-- preferred language fields -->
                                        <label for="profilePreferredLanguageEdit"><b>* <?php echo $translationsSettings['settings_sidebar_profile_preferredLanguage_label']; ?></b></label>
                                        <select class="form-control" name="profilePreferredLanguageEdit">
                                            <option value="en" <?php if ($_SESSION["preferred_language"] == "en") { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_profile_preferredLanguage_option1']; ?></option>
                                            <option value="pt" <?php if ($_SESSION["preferred_language"] == "pt") { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_profile_preferredLanguage_option2']; ?></option>
                                        </select required>

                                        * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                        <button type="submit" class="btn btn-success" name="editProfile"><?php echo $translationsSettings['settings_sidebar_profile_editProfile_title']; ?></button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>

                    <!-- Strava button -->
                    <?php if ($_SESSION["is_strava_linked"] == 1) { ?>
                        <div class="mt-2">
                            <span class="fs-6">Strava already linked</span>
                        </div>
                    <?php } ?>
                    <a class="mt-2 w-100 btn <?php if ($_SESSION["is_strava_linked"] == 1) {
                                                    echo 'disabled';
                                                } ?>" style="--bs-btn-bg: #FC4C02; --bs-btn-active-bg: #FC4C02; --bs-btn-hover-bg: #FC4C02; --bs-btn-disabled-bg: #FC4C02; --bs-btn-disabled-border-color: #FC4C02;" href="../settings/settings.php?profileSettings=1&linkStrava=1" <?php if ($_SESSION["is_strava_linked"] == 1) {
                                                                                                                                                                                                                                                                                                                                                    echo 'aria-disabled="true"';
                                                                                                                                                                                                                                                                                                                                                } ?> role="button"><img src="../img/strava/btn_strava_connectwith_orange.png" alt="Link with strava button" width="65%" height="65%"></a>
                </div>

                <!-- Profile attributes -->
                <div class="col">
                    <h2><?php echo ($_SESSION["name"]); ?></h2>
                    <p><b><?php echo $translationsSettings['settings_sidebar_profile_username_subtitle']; ?></b><?php echo ($_SESSION["username"]); ?></p>
                    <p><b><?php echo $translationsSettings['settings_sidebar_profile_email_subtitle']; ?></b><?php echo ($_SESSION["email"]); ?></p>
                    <p><b><?php echo $translationsSettings['settings_sidebar_profile_birthdate_subtitle']; ?></b><?php
                                                                                                                    if (isset($_SESSION["birthdate"]) && !empty($_SESSION["birthdate"])) {
                                                                                                                        echo date("d/m/Y", strtotime($_SESSION["birthdate"]));
                                                                                                                    } else {
                                                                                                                        echo "N/A"; // Or any default value you prefer when birthdate is not set
                                                                                                                    }
                                                                                                                    ?></p>
                    <p><b><?php echo $translationsSettings['settings_sidebar_profile_city_subtitle']; ?></b><?php echo ($_SESSION["city"]); ?></p>
                    <p><b><?php echo $translationsSettings['settings_sidebar_profile_gender_subtitle']; ?></b><?php if ($_SESSION["gender"] == 1) {
                                                                                                                    echo $translationsSettings['settings_sidebar_profile_gender_male'];
                                                                                                                } else {
                                                                                                                    echo $translationsSettings['settings_sidebar_profile_gender_female'];
                                                                                                                } ?></p>
                    <p><b><?php echo $translationsSettings['settings_sidebar_profile_preferredlanguage_subtitle']; ?></b><?php echo ($_SESSION["preferred_language"]); ?></p>
                    <p><b><?php echo $translationsSettings['settings_sidebar_profile_access_type_subtitle']; ?></b> <?php if ($_SESSION["access_type"] == 1) {
                                                                                                                            echo $translationsSettings['settings_sidebar_profile_access_type_regular_user'];
                                                                                                                        } else {
                                                                                                                            if ($_SESSION["access_type"] == 2) {
                                                                                                                                echo $translationsSettings['settings_sidebar_profile_access_type_admin'];
                                                                                                                            } else {
                                                                                                                                if ($_SESSION["access_type"] == 3) {
                                                                                                                                    echo $translationsSettings['settings_sidebar_profile_access_type_teacher'];
                                                                                                                                } else {
                                                                                                                                    echo $translationsSettings['settings_sidebar_profile_access_type_parent'];
                                                                                                                                }
                                                                                                                            }
                                                                                                                        } ?>
                </div>
            </div>
        </div>

        <!-- gear zone -->
        <div class="col" id="divGearSettings" style="display: <?php if (isset($_GET["gearSettings"])) {
                                                                    echo "block";
                                                                } else {
                                                                    echo "none";
                                                                } ?>;">
            <!-- Error banners -->
            <?php if ($gears == -1 || $gears == -2 || $editGearAction == -1 || $editGearAction == -2 || $editGearAction == -3 || $deleteGearAction == -1 || $deleteGearAction == -2 || $deleteGearAction == -3 || $addGearAction == -1 || $addGearAction == -2 || $addGearAction == -3) { ?>
                <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
                    <i class="fa-solid fa-circle-exclamation me-1"></i>
                    <div>
                        <?php if ($gears == -1 || $addGearAction == -1 || $editGearAction == -1 || $deleteGearAction == -1) { ?>
                            API ERROR | <?php echo $translationsSettings['settings_sidebar_gear_API_error_-1']; ?> (-1).
                        <?php } else { ?>
                            <?php if ($gears == -2 || $addGearAction == -2 || $editGearAction == -2 || $deleteGearAction == -2) { ?>
                                API ERROR | <?php echo $translationsSettings['settings_sidebar_gear_API_error_-2']; ?> (-2).
                            <?php } else { ?>
                                <?php if ($editGearAction == -3) { ?>
                                    <?php echo $translationsSettings['settings_sidebar_gear_error_editGear_-3']; ?> (-3).
                                <?php } else { ?>
                                    <?php if ($addGearAction == -3) { ?>
                                        <?php echo $translationsSettings['settings_sidebar_gear_error_addGear_-3']; ?> (-3).
                                    <?php } ?>
                                <?php } ?>
                            <?php } ?>
                        <?php } ?>
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                </div>
            <?php } ?>

            <!-- Info banners -->
            <?php if ($gears == NULL || (isset($_GET["invalidGear"]) && $_GET["invalidGear"] == 1)) { ?>
                <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
                    <i class="fa-solid fa-triangle-exclamation me-1"></i>
                    <div>
                        <?php if ($gears == NULL) { ?>
                            <?php echo $translationsSettings['settings_sidebar_gear_info_searchGear_NULL']; ?> (NULL).
                        <?php } else { ?>
                            <?php if (isset($_GET["invalidGear"]) && $_GET["invalidGear"] == 1) { ?>
                                <?php echo $translationsSettings['settings_sidebar_gear_info_fromGear_invalidGear']; ?> (1).
                            <?php } ?>
                        <?php } ?>
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                </div>
            <?php } ?>

            <!-- Success banners -->
            <?php if ($addGearAction == 0 || $editGearAction == 0 || $deleteGearAction == 0) { ?>
                <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
                    <div>
                        <i class="fa-regular fa-circle-check me-1"></i>
                        <?php if ($addGearAction == 0) { ?>
                            <?php echo $translationsSettings['settings_sidebar_gear_success_gearAdded']; ?>
                        <?php } else { ?>
                            <?php if ($editGearAction == 0) { ?>
                                <?php echo $translationsSettings['settings_sidebar_gear_success_gearEdited']; ?>
                            <?php } else { ?>
                                <?php if ($deleteGearAction == 0) { ?>
                                    <?php echo $translationsSettings['settings_sidebar_gear_success_gearDeleted']; ?>
                                <?php } ?>
                            <?php } ?>
                        <?php } ?>
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                </div>
            <?php } ?>

            <div class="row row-gap-3">
                <div class="col-lg-4 col-md-12">
                    <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearModal"><?php echo $translationsSettings['settings_sidebar_gear_button_addGear']; ?></a>

                    <!-- Modal add gear -->
                    <div class="modal fade" id="addGearModal" tabindex="-1" aria-labelledby="addGearModal" aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="addGearModal"><?php echo $translationsSettings['settings_sidebar_gear_modal_addGear_title']; ?></h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <form action="../settings/settings.php?addGear=1&gearSettings=1" method="post" enctype="multipart/form-data">
                                    <div class="modal-body">
                                        <!-- brand fields -->
                                        <label for="gearBrandAdd"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_brandLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="gearBrandAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_brandPlaceholder']; ?>" maxlength="45" value="<?php echo ($_POST["gearBrandAdd"]); ?>">
                                        <!-- model fields -->
                                        <label for="gearModelAdd"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_modelLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="gearModelAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_modelPlaceholder']; ?>" maxlength="45" value="<?php echo ($_POST["gearModelAdd"]); ?>">
                                        <!-- nickname fields -->
                                        <label for="gearNicknameAdd"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_nicknameLabel']; ?></b></label>
                                        <input class="form-control" type="text" name="gearNicknameAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_nicknamePlaceholder']; ?>" maxlength="45" value="<?php echo ($_POST["gearNicknameAdd"]); ?>">
                                        <!-- gear type fields -->
                                        <label for="gearTypeAdd"><b>* <?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeLabel']; ?></b></label>
                                        <select class="form-control" name="gearTypeAdd">
                                            <option value="1" <?php if ($_POST["gearTypeAdd"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption1']; ?></option>
                                            <option value="2" <?php if ($_POST["gearTypeAdd"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption2']; ?></option>
                                            <option value="3" <?php if ($_POST["gearTypeAdd"] == 3) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption3']; ?></option>
                                        </select required>
                                        <!-- date fields -->
                                        <label for="gearDateAdd"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_dateLabel']; ?></b></label>
                                        <input class="form-control" type="date" name="gearDateAdd" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_datePlaceholder']; ?>" value="<?php echo ($_POST["gearDateAdd"]); ?>" required>
                                        * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                        <button type="submit" class="btn btn-success" name="addGear"><?php echo $translationsSettings['settings_sidebar_gear_modal_addGear_title']; ?></button>
                                    </div>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col">
                    <form action="../settings/settings.php?gearSettings=1" method="post" class="d-flex">
                        <input class="form-control me-2" type="text" name="gearNickname" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_form_searchGear_nicknamePlaceholder']; ?>" required>
                        <button class="btn btn-success" type="submit" name="gearSearch"><?php echo $translationsSettings['settings_sidebar_gear_button_searchGear']; ?></button>
                        <?php if (isset($_POST["gearSearch"])) { ?>
                            <a class="ms-2 w-25 btn btn-primary" href="../settings/settings.php?gearSettings=1" role="button"><?php echo $translationsTemplateTop['template_top_global_button_listAll']; ?></a>
                        <?php } ?>
                    </form>
                </div>
            </div>
            <!-- gears list zone -->
            <?php if ($gears != NULL && $gears != -1 && $gears != -2 && $gears != -3) { ?>
                <!-- title zone -->
                <br>
                <p><?php echo $translationsSettings['settings_sidebar_gear_list_title1']; ?> <?php echo ($numGears); ?> <?php echo $translationsSettings['settings_sidebar_gear_list_title2']; ?> (<?php echo $numRecords; ?> <?php echo $translationsSettings['settings_sidebar_gear_list_title3']; ?>:</p>
                <!-- list zone -->
                <ul class="list-group list-group-flush">
                    <?php foreach ($gears as $gear) { ?>
                        <li class="list-group-item d-flex justify-content-between">
                            <div class="d-flex align-items-center">
                                <img src=<?php echo ("../img/avatar/male1.png"); ?> alt="gearPicture" class="rounded-circle" width="55" height="55">
                                <div class="ms-3">
                                    <div class="fw-bold">
                                        <?php echo ($gear["nickname"]); ?>
                                    </div>
                                    <b><?php echo $translationsSettings['settings_sidebar_settings_sidebar_gear_type']; ?></b><?php if ($gear["gear_type"] == 1) {
                                                                                                                                    echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption1'];
                                                                                                                                } else {
                                                                                                                                    if ($gear["gear_type"] == 2) {
                                                                                                                                        echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption2'];
                                                                                                                                    } else {
                                                                                                                                        if ($gear["gear_type"] == 3) {
                                                                                                                                            echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption3'];
                                                                                                                                        }
                                                                                                                                    }
                                                                                                                                } ?>
                                </div>
                            </div>
                            <div>
                                <!-- gear status zone -->
                                <?php if ($gear["is_active"] == 1) { ?>
                                    <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle"><?php echo $translationsSettings['settings_sidebar_gear_list_isactive']; ?></span>
                                <?php } else { ?>
                                    <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle"><?php echo $translationsSettings['settings_sidebar_gear_list_isinactive']; ?></span>
                                <?php } ?>

                                <!-- edit gear zone -->
                                <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editGearModal<?php echo ($gear["id"]); ?>"><i class="fa-solid fa-pen-to-square"></i></a>

                                <!-- Modal edit gear -->
                                <div class="modal fade" id="editGearModal<?php echo ($gear["id"]); ?>" tabindex="-1" aria-labelledby="editGearModal" aria-hidden="true">
                                    <div class="modal-dialog">
                                        <div class="modal-content">
                                            <div class="modal-header">
                                                <h1 class="modal-title fs-5" id="editGearModal<?php echo ($gear["id"]); ?>"><?php echo $translationsSettings['settings_sidebar_gear_modal_editGear_title']; ?></h1>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                            </div>
                                            <form action="../settings/settings.php?gearID=<?php echo ($gear["id"]); ?>&editGear=1&gearSettings=1" method="post" enctype="multipart/form-data">
                                                <div class="modal-body">
                                                    <!-- brand fields -->
                                                    <label for="gearBrandEdit"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_brandLabel']; ?></b></label>
                                                    <input class="form-control" type="text" name="gearBrandEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_brandPlaceholder']; ?>" maxlength="45" value="<?php echo ($gear["brand"]); ?>">
                                                    <!-- model fields -->
                                                    <label for="gearModelEdit"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_modelLabel']; ?></b></label>
                                                    <input class="form-control" type="text" name="gearModelEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_modelPlaceholder']; ?>" maxlength="45" value="<?php echo ($gear["model"]); ?>">
                                                    <!-- nickname fields -->
                                                    <label for="gearNicknameEdit"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_nicknameLabel']; ?></b></label>
                                                    <input class="form-control" type="text" name="gearNicknameEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_nicknamePlaceholder']; ?>" maxlength="45" value="<?php echo ($gear["nickname"]); ?>">
                                                    <!-- gear type fields -->
                                                    <label for="gearTypeEdit"><b>* <?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeLabel']; ?></b></label>
                                                    <select class="form-control" name="gearTypeEdit">
                                                        <option value="1" <?php if ($gear["gear_type"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption1']; ?></option>
                                                        <option value="2" <?php if ($gear["gear_type"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption2']; ?></option>
                                                        <option value="3" <?php if ($gear["gear_type"] == 3) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_gearTypeOption3']; ?></option>
                                                    </select required>
                                                    <!-- date fields -->
                                                    <label for="gearDateEdit"><b><?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_dateLabel']; ?></b></label>
                                                    <input class="form-control" type="date" name="gearDateEdit" placeholder="<?php echo $translationsSettings['settings_sidebar_gear_modal_addEditGear_datePlaceholder']; ?>" value="<?php echo date("Y-m-d", strtotime($gear["created_at"])); ?>" required>
                                                    <!-- gear is_active fields -->
                                                    <label for="gearIsActiveEdit"><b>* <?php echo $translationsSettings['settings_sidebar_gear_modal_editGear_gearIsActiveLabel']; ?></b></label>
                                                    <select class="form-control" name="gearIsActiveEdit">
                                                        <option value="1" <?php if ($gear["is_active"] == 1) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_editGear_gearIsActiveOption1']; ?></option>
                                                        <option value="2" <?php if ($gear["is_active"] == 2) { ?> selected="selected" <?php } ?>><?php echo $translationsSettings['settings_sidebar_gear_modal_editGear_gearIsActiveOption2']; ?></option>
                                                    </select required>
                                                    * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                                </div>
                                                <div class="modal-footer">
                                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                                    <button type="submit" class="btn btn-success" name="editGear"><?php echo $translationsSettings['settings_sidebar_gear_modal_editGear_title']; ?></button>
                                                </div>
                                            </form>
                                        </div>
                                    </div>
                                </div>

                                <!-- delete gear zone -->
                                <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteGearModal<?php echo ($gear["id"]); ?>"><i class="fa-solid fa-trash-can"></i></a>

                                <!-- Modal delete gear -->
                                <div class="modal fade" id="deleteGearModal<?php echo ($gear["id"]); ?>" tabindex="-1" aria-labelledby="deleteGearModal<?php echo ($user["id"]); ?>" aria-hidden="true">
                                    <div class="modal-dialog">
                                        <div class="modal-content">
                                            <div class="modal-header">
                                                <h1 class="modal-title fs-5" id="deleteGearModal<?php echo ($gear["id"]); ?>"><?php echo $translationsSettings['settings_sidebar_gear_modal_deleteGear_title']; ?></h1>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                            </div>
                                            <div class="modal-body">
                                                <?php echo $translationsSettings['settings_sidebar_gear_modal_deleteGear_body']; ?> <b><?php echo ($gear["nickname"]); ?></b>
                                            </div>
                                            <div class="modal-footer">
                                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                                <a type="button" class="btn btn-danger" href="../settings/settings.php?gearID=<?php echo ($gear["id"]); ?>&deleteGear=1&gearSettings=1"><?php echo $translationsSettings['settings_sidebar_gear_modal_deleteGear_title']; ?></a>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </li>
                    <?php } ?>
                </ul>
                <?php if (!isset($_POST["gearSearch"])) { ?>
                    <br>
                    <nav>
                        <ul class="pagination justify-content-center">
                            <li class="page-item <?php if ($pageNumberGears == 1) {
                                                        echo "disabled";
                                                    } ?>"><a class="page-link" href="?pageNumberGears=1">«</a></li>
                            <?php for ($i = 1; $i <= $total_pages; $i++) { ?>
                                <li class="page-item <?php if ($i == $pageNumberGears) {
                                                            echo "active";
                                                        } ?>"><a class="page-link" href="?pageNumberGears=<?php echo ($i); ?>"><?php echo ($i); ?></a></li>
                            <?php } ?>
                            <li class="page-item <?php if ($pageNumberGears == $total_pages) {
                                                        echo "disabled";
                                                    } ?>"><a class="page-link" href="?pageNumberGears=<?php echo ($total_pages); ?>">»</a></li>
                        </ul>
                    </nav>
                <?php } ?>
            <?php } ?>
        </div>

        <hr class="d-lg-none">
    </div>
    <div>
        <!--<hr class="d-lg-none">-->
        <button onclick="window.history.back();" type="button" class="w-100 btn btn-primary d-lg-none"><?php echo $translationsTemplateTop['template_top_global_back']; ?></button>
    </div>
</div>

<script>
    document.addEventListener("DOMContentLoaded", function(event) {
        if (window.location.search.indexOf("users=1") !== -1) {
            changeActive(null, 'divUsers');
        }
        if (window.location.search.indexOf("global=1") !== -1) {
            changeActive(null, 'divGlobal');
        }
        if (window.location.search.indexOf("profileSettings=1") !== -1) {
            changeActive(null, 'divProfileSettings');
        }
        if (window.location.search.indexOf("gearSettings=1") !== -1) {
            changeActive(null, 'divGearSettings');
        }
    });

    function changeActive(event, div) {
        // Prevent the default link behavior
        if (event) event.preventDefault();

        // Remove the active class from all nav items
        var navItems = document.querySelectorAll('#sidebarNav .nav-item');
        navItems.forEach(function(item) {
            if (event) item.querySelector('.nav-link').classList.remove('active');
        });

        // Add the active class to the clicked nav item
        if (event) event.target.classList.add('active');

        if (div == "divUsers") {
            document.getElementById("divUsers").style.display = 'block';
            document.getElementById("divGlobal").style.display = 'none';
            document.getElementById("divProfileSettings").style.display = 'none';
            document.getElementById("divGearSettings").style.display = 'none';
        } else {
            if (div == "divGlobal") {
                document.getElementById("divUsers").style.display = 'none';
                document.getElementById("divGlobal").style.display = 'block';
                document.getElementById("divProfileSettings").style.display = 'none';
                document.getElementById("divGearSettings").style.display = 'none';
            } else {
                if (div == "divProfileSettings") {
                    document.getElementById("divUsers").style.display = 'none';
                    document.getElementById("divGlobal").style.display = 'none';
                    document.getElementById("divProfileSettings").style.display = 'block';
                    document.getElementById("divGearSettings").style.display = 'none';
                } else {
                    if (div == "divGearSettings") {
                        document.getElementById("divUsers").style.display = 'none';
                        document.getElementById("divGlobal").style.display = 'none';
                        document.getElementById("divProfileSettings").style.display = 'none';
                        document.getElementById("divGearSettings").style.display = 'block';
                    }
                }
            }
        }
    }
</script>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>