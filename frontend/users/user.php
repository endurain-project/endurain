<?php
if (!isset($_SESSION)) {
    session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "user";
$last4weeksNumberActivities = 0;
$numUserActivities = 0;
$userActivities = [];

if (!isLogged()) {
    header("Location: ../login.php");
}

if (!isTokenValid($_SESSION["token"])) {
    header("Location: ../logout.php?sessionExpired=1");
}

// Load the language file based on the user's preferred language
switch ($_SESSION["preferred_language"]) {
    case 'en':
        $translationsUsersUser = include $_SERVER['DOCUMENT_ROOT'] . '/lang/users/user/en.php';
        break;
    case 'pt':
        $translationsUsersUser = include $_SERVER['DOCUMENT_ROOT'] . '/lang/users/user/pt.php';
        break;
        // ...
    default:
        $translationsUsersUser = include $_SERVER['DOCUMENT_ROOT'] . '/lang/users/user/en.php';
}

$user = getUserFromId($_GET["userID"]);
$numUserActivities = 0;
if ($numUserActivities > 0) {
    #$userActivities = 0;
}

?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<div class="container mt-4">
    <div class="row">
        <div class="col">
            <div class="vstack d-flex justify-content-center">
                <div class="d-flex justify-content-center">
                    <img src=<?php if (is_null($_SESSION["photo_path"])) {
                                    if ($_SESSION["gender"] == 1) {
                                        echo ("../img/avatar/male1.png");
                                    } else {
                                        echo ("../img/avatar/female1.png");
                                    }
                                } else {
                                    echo ($_SESSION["photo_path"]);
                                } ?> alt="userPicture" class="rounded-circle" width="120" height="120">
                </div>
                <div class="text-center mt-3 mb-3">
                    <?php echo $user[0]["name"]; ?>
                </div>
            </div>
        </div>
        <div class="col">

        </div>
        <div class="col">

        </div>
    </div>
    <div>
        <p>This week activities</p>
    </div>
</div>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>