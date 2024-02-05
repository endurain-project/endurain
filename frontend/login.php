<?php
if (!isset($_SESSION)) {
    session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "login";

if (isLogged()) {
    header("Location: ../index.php");
}

// Load the en language file 
$translationsLogin = include $_SERVER['DOCUMENT_ROOT'] . '/lang/login/en.php';

$error = 0;

if (isset($_POST["loginUsername"]) && isset($_POST["loginPassword"])) {
    clearUserRelatedInfoSession();
    $hashPassword = hash("sha256", $_POST["loginPassword"]);
    $neverExpires = false;
    if (isset($_POST["loginNeverExpires"]) && $_POST["loginNeverExpires"] === "on") {
        $neverExpires = true;
    }
    $result = loginUser($_POST["loginUsername"], $hashPassword, $neverExpires);

    if ($result[1] === 200) {
        $responseContent = json_decode($result[0], true);
        if (isset($responseContent['access_token'])) {
            $error = setUserRelatedInfoSession($responseContent['access_token']);
            if ($error == 0) {
                header("Location: ../index.php");
                die();
            }
        }else{
            $error = 1;
        }
    } else {
        if ($result[1] === 400) {
            if(json_decode($result[0], true)["error"]["message"] === "User is not active"){
                $error = 2;
            }else{
                if(json_decode($result[0], true)["error"]["message"] == "Incorrect username or password"){
                    $error = 3;
                }
            }
        }else{
            $error = 4;
        }
    }
}
?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<main class="form-signin w-100 m-auto text-center p-5" style="max-width: 500px">
    <!-- Error banners -->
    <?php if ($error == 1 || $error == 2 || $error == 3 || $error == 4 || $error == -1 || $error == -3 || $error == -3) { ?>
        <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
            <i class="fa-solid fa-circle-exclamation me-1"></i>
            <div>
                <?php if ($error == 1) { ?>
                    <?php echo $translationsLogin['login_error_access_token_not_set']; ?> (1).
                <?php } else { ?>
                    <?php if ($error == 2) { ?>
                        <?php echo $translationsLogin['login_error_user_inactive']; ?> (2).
                    <?php } else { ?>
                        <?php if ($error == 3) { ?>
                            <?php echo $translationsLogin['login_error_incorrect_user_credentials']; ?> (3).
                        <?php } else { ?>
                            <?php if ($error == 4) { ?>
                                <?php echo $translationsLogin['login_error_undefined']; ?> (4).
                            <?php } else { ?>
                                <?php if ($error == -1) { ?>
                                    <?php echo $translationsLogin['login_API_error_-1']; ?> (-1).
                                <?php } else { ?>
                                    <?php if ($error == -2) { ?>
                                        <?php echo $translationsLogin['login_API_error_-2']; ?> (-2).
                                    <?php } else { ?>
                                        <?php if ($error == -3) { ?>
                                            <?php echo $translationsLogin['login_API_error_-3']; ?> (-3).
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
    <?php if (isset($_GET["sessionExpired"]) && $_GET["sessionExpired"] == 1) { ?>
        <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
            <i class="fa-solid fa-triangle-exclamation me-1"></i>
            <div>
                <?php if (isset($_GET["sessionExpired"]) && $_GET["sessionExpired"] == 1) { ?>
                    <?php echo $translationsLogin['login_info_session expired']; ?>.
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>
    
    <form action="../login.php" method="post">
        <h1>Endurain</h1>
        <p><?php echo $translationsLogin['login_subtitle']; ?></p>
        <br>

        <div class="form-floating">
            <input type="text" class="form-control" id="floatingInput" placeholder="<?php echo $translationsLogin['login_insert_username']; ?>" name="loginUsername" required>
            <label for="loginUsername"><?php echo $translationsLogin['login_insert_username']; ?></label>
        </div>
        <br>
        <div class="form-floating">
            <input type="password" class="form-control" placeholder="<?php echo $translationsLogin['login_password']; ?>" name="loginPassword" required>
            <label for="loginPassword"><?php echo $translationsLogin['login_password']; ?></label>
        </div>
        <br>
        <div class="form-check">
            <input type="checkbox" class="form-check-input" name="loginNeverExpires">
            <label class="form-check-label" for="loginNeverExpires"><?php echo $translationsLogin['login_neverExpires']; ?></label>
        </div>
        <br>
        <button class="w-100 btn btn-lg btn-primary" type="submit"><?php echo $translationsLogin['login_login']; ?></button>
        <!--<div>
            <br>
            <p><?php echo $translationsLogin['login_signup_text']; ?></p>
            <button class="w-100 btn btn-lg btn-primary disabled" type="submit"><?php echo $translationsLogin['login_signup_button']; ?></button>
        </div>-->
    </form>
</main>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>