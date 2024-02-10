<?php
if (!isset($_SESSION)) {
    session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "user";
$last4weeksNumberActivities = 0;
$numUserActivities = 0;
$userActivities = [];
$followUserResult = -9000;
$deleteFollowUserResult = -9000;
$acceptFollowRequestResult = -9000;

if (!isLogged()) {
    header("Location: ../login.php");
    die();
}

if (!isTokenValid($_SESSION["token"])) {
    header("Location: ../logout.php?sessionExpired=1");
    die();
}

// if userID not set redirect to index.php
if (!isset($_GET["userID"])) {
    header("Location: ../index.php");
    die();
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
if ($user == null) {
    header("Location: ../index.php?userNotFound=1");
}


if (isset($_GET["followUser"]) && $_GET["followUser"] == 1) {
    $followUserResult = createUserFollowsSpecificUser($_GET["userID"]);
}

if ((isset($_GET["cancelFollowUser"]) && $_GET["cancelFollowUser"] == 1) || (isset($_GET["unfollowUser"]) && $_GET["unfollowUser"] == 1) || (isset($_GET["declineUserRequest"]) && $_GET["declineUserRequest"] == 1) || (isset($_GET["deleteFollower"]) && $_GET["deleteFollower"] == 1) || (isset($_GET["deleteFollowing"]) && $_GET["deleteFollowing"] == 1)) {
    if((isset($_GET["declineUserRequest"]) && $_GET["declineUserRequest"] == 1) || (isset($_GET["deleteFollower"]) && $_GET["deleteFollower"] == 1) || (isset($_GET["deleteFollowing"]) && $_GET["deleteFollowing"] == 1)){
        if(isset($_GET["targetUserID"])){
            if(isset($_GET["deleteFollowing"]) && $_GET["deleteFollowing"] == 1){
                $deleteFollowUserResult = deleteUserFollowsSpecificUser($_GET["userID"], $_GET["targetUserID"]);
            }else{
                $deleteFollowUserResult = deleteUserFollowsSpecificUser($_GET["targetUserID"], $_GET["userID"]);
            }
        }
    }else{
        $deleteFollowUserResult = deleteUserFollowsSpecificUser($_SESSION["id"], $_GET["userID"]);
    }
}

if (isset($_GET["acceptUserRequest"]) && $_GET["acceptUserRequest"] == 1) {
    $acceptFollowRequestResult = acceptUserFollowsSpecificUser($_GET["userID"], $_GET["targetUserID"]);
}

$numUserActivitiesThisMonth = getUserActivitiesThisMonthNumber($_GET["userID"]);

if ($_GET["userID"] != $_SESSION["id"]) {
    $userFollowState = getStatusUserFollowsSpecificUser($_GET["userID"]);
}

if (!isset($_GET["week"])) {
    $_GET["week"] = 0;
}

$weekActivities = getUserActivitiesWeek($_GET["userID"], $_GET["week"]);

$thisWeekDistances = getUserActivitiesThisWeekDistances($_GET["userID"]);
$thisMonthDistances = getUserActivitiesThisMonthDistances($_GET["userID"]);

// Default week offset is 0 (current week)
$weekOffset = isset($_GET["week"]) ? intval($_GET["week"]) : 0;

// Calculate the first day of the desired week
$firstDay = date('Y-m-d', strtotime("monday this week - {$weekOffset} weeks"));

// Calculate the last day of the desired week
$lastDay = date('Y-m-d', strtotime("sunday this week - {$weekOffset} weeks"));

// Format the dates as desired (day month year)
$formattedFirstDay = date('d F Y', strtotime($firstDay));
$formattedLastDay = date('d F Y', strtotime($lastDay));

$userFollowersCountAll = getUserFollowersCountAll($_GET["userID"]);
$userFollowersCount = getUserFollowersCount($_GET["userID"]);
$userFollowersAll = getUserFollowersAll($_GET["userID"]);
$userFollowingCountAll = getUserFollowingCountAll($_GET["userID"]);
$userFollowingCount = getUserFollowingCount($_GET["userID"]);
$userFollowingAll = getUserFollowingAll($_GET["userID"]);
?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<div class="container mt-4">
    <!-- Error banners -->
    <?php if ($followUserResult == -1 || $followUserResult == -2 || $deleteFollowUserResult == -1 || $deleteFollowUserResult == -2 || $acceptFollowRequestResult == -1 || $acceptFollowRequestResult == -2) { ?>
        <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
            <i class="fa-solid fa-circle-exclamation me-1"></i>
            <div>
                <?php if ($followUserResult == -1 || $deleteFollowUserResult == -1 || $acceptFollowRequestResult == -1) { ?>
                    API ERROR |
                    <?php echo $translationsUsersUser['user_follow_API_error_-1']; ?> (-1).
                <?php } else { ?>
                    <?php if ($followUserResult == -2 || $deleteFollowUserResult == -2 || $acceptFollowRequestResult == -2) { ?>
                        API ERROR |
                        <?php echo $translationsUsersUser['user_follow_API_error_-2']; ?> (-2).
                    <?php } ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>

    <!-- Info banners -->

    <!-- Success banners -->
    <?php if (($followUserResult != -9000 && $followUserResult != -1 && $followUserResult != -2) || ($deleteFollowUserResult != -9000 && $deleteFollowUserResult != -1 && $deleteFollowUserResult != -2) || ($acceptFollowRequestResult != -9000 && $acceptFollowRequestResult != -1 && $acceptFollowRequestResult != -2)) { ?>
        <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
            <div>
                <i class="fa-regular fa-circle-check me-1"></i>
                <?php if ($followUserResult != -9000 && $followUserResult != -1 && $followUserResult != -2) { ?>
                    <?php echo $translationsUsersUser['user_follow_success']; ?>
                <?php } else { ?>
                    <?php if ($deleteFollowUserResult != -9000 && $deleteFollowUserResult != -1 && $deleteFollowUserResult != -2) { ?>
                        <?php if(isset($_GET["declineUserRequest"]) && $_GET["declineUserRequest"] == 1){ ?>
                            <?php echo $translationsUsersUser['user_follow_request_declined']; ?>
                        <?php }else{ ?>
                            <?php echo $translationsUsersUser['user_unfollow_success']; ?>
                        <?php } ?>
                    <?php } else { ?>
                        <?php if ($acceptFollowRequestResult != -9000 && $acceptFollowRequestResult != -1 && $acceptFollowRequestResult != -2) { ?>
                            <?php echo $translationsUsersUser['user_follow_request_accepted']; ?>
                        <?php } ?>
                    <?php } ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>

    <div class="row align-items-center">
        <div class="col">
            <div class="vstack d-flex justify-content-center">
                <div class="d-flex justify-content-center">
                    <img src=<?php if (is_null($user["photo_path"])) {
                        if ($user["gender"] == 1) {
                            echo ("../img/avatar/male1.png");
                        } else {
                            echo ("../img/avatar/female1.png");
                        }
                    } else {
                        echo ($user["photo_path"]);
                    } ?> alt="userPicture" class="rounded-circle" width="120"
                        height="120">
                </div>
                <div class="text-center mt-3 mb-3">
                    <h3>
                        <?php echo $user["name"]; ?>
                    </h3>
                    <?php if (isset($user["city"])) { ?>
                        <span class="fw-lighter">
                            <i class="fa-solid fa-location-dot"></i>
                            <?php echo $user["city"]; ?>
                        </span>
                    <?php } ?>
                </div>
            </div>
        </div>
        <div class="col">
            <div class="vstack d-flex align-middle text-center">
                <span class="fw-lighter">
                    <?php echo $translationsUsersUser['user_stats_numberActivitiesMonth']; ?>
                </span>
                <h1>
                    <?php echo $numUserActivitiesThisMonth; ?>
                </h1>
                <!--<hr class="mb-2 mt-2">-->
                <div class="row align-items-center">
                    <div class="col">
                        <?php if($userFollowersCount){ ?>
                            <?php echo $userFollowersCount; ?>
                        <?php }else{ ?>
                            0
                        <?php } ?>
                        <br>
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_main_nav_following']; ?>
                        </span>
                    </div>
                    <div class="col">
                        <?php if($userFollowingCount){ ?>
                            <?php echo $userFollowingCount; ?>
                        <?php }else{ ?>
                            0
                        <?php } ?>
                        <br>
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_main_nav_followers']; ?>
                        </span>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-sm">
            <div class="d-none d-lg-block mt-3 mb-3 d-flex justify-content-center">
                <!-- this week distances zone -->
                <span class="fw-lighter">
                    <?php echo $translationsUsersUser['user_distances_zone_thisWeekDistances_title']; ?>
                </span>
                <div class="row mb-3">
                    <div class="col">
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_distances_zone_thisWeekDistances_run']; ?>
                        </span>
                        <br>
                        <?php if (isset($thisWeekDistances)) { ?>
                            <?php echo number_format(($thisWeekDistances["run"] / 1000), 2); ?> km
                        <?php } else { ?>
                            0 km
                        <?php } ?>
                    </div>
                    <div class="col border-start border-opacity-50">
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_distances_zone_thisWeekDistances_bike']; ?>
                        </span>
                        <br>
                        <?php if (isset($thisWeekDistances)) { ?>
                            <?php echo number_format(($thisWeekDistances["bike"] / 1000), 2); ?> km
                        <?php } else { ?>
                            0 km
                        <?php } ?>
                    </div>
                    <div class="col border-start border-opacity-50">
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_distances_zone_thisWeekDistances_swim']; ?>
                        </span>
                        <br>
                        <?php if (isset($thisWeekDistances)) { ?>
                            <?php if ($thisWeekDistances["swim"] > 10000) { ?>
                                <?php echo number_format(($thisWeekDistances["swim"] / 1000), 2); ?> km
                            <?php } else { ?>
                                <?php echo $thisWeekDistances["swim"]; ?> m
                            <?php } ?>
                        <?php } else { ?>
                            0 m
                        <?php } ?>
                    </div>
                </div>
                <!-- this month distances zone -->
                <span class="fw-lighter">
                    <?php echo $translationsUsersUser['user_distances_zone_thisMonthDistances_title']; ?>
                </span>
                <div class="row">
                    <div class="col">
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_distances_zone_thisWeekDistances_run']; ?>
                        </span>
                        <br>
                        <?php if (isset($thisMonthDistances["run"])) { ?>
                            <?php echo number_format(($thisMonthDistances["run"] / 1000), 2); ?> km
                        <?php } else { ?>
                            0 km
                        <?php } ?>
                    </div>
                    <div class="col border-start border-opacity-50">
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_distances_zone_thisWeekDistances_bike']; ?>
                        </span>
                        <br>
                        <?php if (isset($thisMonthDistances["run"])) { ?>
                            <?php echo number_format(($thisMonthDistances["bike"] / 1000), 2); ?> km
                        <?php } else { ?>
                            0 km
                        <?php } ?>
                    </div>
                    <div class="col border-start border-opacity-50">
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_distances_zone_thisWeekDistances_swim']; ?>
                        </span>
                        <br>
                        <?php if (isset($thisMonthDistances["run"])) { ?>
                            <?php if ($thisMonthDistances["swim"] > 10000) { ?>
                                <?php echo number_format(($thisMonthDistances["swim"] / 1000), 2); ?> km
                            <?php } else { ?>
                                <?php echo $thisMonthDistances["swim"]; ?> m
                            <?php } ?>
                        <?php } else { ?>
                            0 m
                        <?php } ?>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- navbar for user page -->
    <div>
        <ul class="nav nav-pills mb-3 justify-content-center" id="pills-tab" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="pills-activities-tab" data-bs-toggle="pill"
                    data-bs-target="#pills-activities" type="button" role="tab" aria-controls="pills-activities"
                    aria-selected="true">
                    <?php echo $translationsUsersUser['user_main_nav_activities']; ?>
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="pills-following-tab" data-bs-toggle="pill"
                    data-bs-target="#pills-following" type="button" role="tab" aria-controls="pills-following"
                    aria-selected="false">
                    <?php echo $translationsUsersUser['user_main_nav_following']; ?>
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="pills-followers-tab" data-bs-toggle="pill"
                    data-bs-target="#pills-followers" type="button" role="tab" aria-controls="pills-followers"
                    aria-selected="false">
                    <?php echo $translationsUsersUser['user_main_nav_followers']; ?>
                </button>
            </li>
            <?php if ($_GET["userID"] == $_SESSION["id"]) { ?>
                <li class="nav-item" role="presentation">
                    <a class="btn nav-link" href="../settings/settings.php?profileSettings=1"><i
                            class="fa-solid fa-gear"></i>
                        <?php echo $translationsUsersUser['user_main_nav_user_settings']; ?>
                    </a>
                </li>
            <?php } else { ?>
                <?php if (!isset($userFollowState) || $userFollowState == -2) { ?>
                    <!-- follow user button -->
                    <li class="nav-item" role="presentation">
                        <a class="btn btn-outline-success h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                            data-bs-target="#followUserModal">
                            <i class="fa-solid fa-user-plus"></i>
                            <?php echo $translationsUsersUser['user_main_nav_followStatus_follow']; ?>
                        </a>
                    </li>

                    <!-- Modal follow user -->
                    <div class="modal fade" id="followUserModal" tabindex="-1" aria-labelledby="followUserModal"
                        aria-hidden="true">
                        <div class="modal-dialog">
                            <div class="modal-content">
                                <div class="modal-header">
                                    <h1 class="modal-title fs-5" id="followUserModal">
                                        <?php echo $translationsUsersUser['user_follow_modal_title']; ?>
                                    </h1>
                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                </div>
                                <div class="modal-body">
                                    <?php echo $translationsUsersUser['user_follow_modal_body']; ?> <b>
                                        <?php echo $user["name"]; ?>
                                    </b>?
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                        <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                    </button>
                                    <a type="button" class="btn btn-success"
                                        href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&followUser=1">
                                        <?php echo $translationsUsersUser['user_follow_modal_title']; ?>
                                    </a>
                                </div>
                            </div>
                        </div>
                    </div>
                <?php } else { ?>
                    <?php if (!$userFollowState["is_accepted"]) {?>
                        <!-- follow user request sent button -->
                        <li class="nav-item" role="presentation">
                            <a class="btn btn-outline-secondary h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                                data-bs-target="#cancelFollowUserModal">
                                <i class="fa-solid fa-user-plus"></i>
                                <?php echo $translationsUsersUser['user_main_nav_followStatus_requestSent']; ?>
                            </a>
                        </li>

                        <!-- Modal follow user request sent -->
                        <div class="modal fade" id="cancelFollowUserModal" tabindex="-1" aria-labelledby="cancelFollowUserModal"
                            aria-hidden="true">
                            <div class="modal-dialog">
                                <div class="modal-content">
                                    <div class="modal-header">
                                        <h1 class="modal-title fs-5" id="cancelFollowUserModal">
                                            <?php echo $translationsUsersUser['user_cancelFollow_modal_title']; ?>
                                        </h1>
                                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                    </div>
                                    <div class="modal-body">
                                        <?php echo $translationsUsersUser['user_cancelFollow_modal_body']; ?> <b>
                                            <?php echo $user["name"]; ?>
                                        </b>?
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                            <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                        </button>
                                        <a type="button" class="btn btn-danger"
                                            href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&cancelFollowUser=1">
                                            <?php echo $translationsUsersUser['user_cancelFollow_modal_title']; ?>
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>
                    <?php } else { ?>
                        <!-- unfollow user button -->
                        <li class="nav-item" role="presentation">
                            <a class="btn btn-outline-danger h-100 ms-2" href="#" role="button" data-bs-toggle="modal"
                                data-bs-target="#unfollowUserModal">
                                <i class="fa-solid fa-user-plus"></i>
                                <?php echo $translationsUsersUser['user_main_nav_followStatus_unfollow']; ?>
                            </a>
                        </li>

                        <!-- Modal unfollow user -->
                        <div class="modal fade" id="unfollowUserModal" tabindex="-1" aria-labelledby="unfollowUserModal"
                            aria-hidden="true">
                            <div class="modal-dialog">
                                <div class="modal-content">
                                    <div class="modal-header">
                                        <h1 class="modal-title fs-5" id="unfollowUserModal">
                                            <?php echo $translationsUsersUser['user_unfollow_modal_title']; ?>
                                        </h1>
                                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                    </div>
                                    <div class="modal-body">
                                        <?php echo $translationsUsersUser['user_unfollow_modal_body']; ?> <b>
                                            <?php echo $user["name"]; ?>
                                        </b>?
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                            <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                        </button>
                                        <a type="button" class="btn btn-danger"
                                            href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&unfollowUser=1">
                                            <?php echo $translationsUsersUser['user_unfollow_modal_title']; ?>
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>
                    <?php } ?>
                <?php } ?>
            <?php } ?>
        </ul>
        <div class="tab-content" id="pills-tabContent">
            <!-- div activities -->
            <div class="tab-pane fade show active" id="pills-activities" role="tabpanel"
                aria-labelledby="pills-activities-tab" tabindex="0">
                <!-- pagination -->
                <nav>
                    <ul class="pagination justify-content-center">
                        <li class="page-item <?php if ($_GET["week"] == 0) {
                            echo "active";
                        } ?>"><a class="page-link" href="?userID=<?php echo $_GET["userID"]; ?>&week=0">
                                <?php echo $translationsUsersUser['user_activities_zone_date_current']; ?>
                            </a></li>

                        <?php if ($_GET["week"] > 2) { ?>
                            <li class="page-item disabled"><a class="page-link">...</a></li>
                        <?php } ?>

                        <?php
                        $currentWeek = isset($_GET["week"]) ? intval($_GET["week"]) : 0;
                        $totalWeeks = 50; // Assuming a total of 52 weeks in a year
                        
                        // Define the range of weeks to display around the current week
                        $weekRange = 1; // You can adjust this value based on your preference
                        
                        // Generate pagination links
                        for ($i = max(1, $currentWeek - $weekRange); $i <= min($totalWeeks, $currentWeek + $weekRange); $i++) {
                            echo '<li class="page-item ';
                            if ($i == $currentWeek) {
                                echo 'active';
                            }
                            echo '"><a class="page-link" href="?userID=' . $_GET["userID"] . '&week=' . $i . '">' . date('d/m', strtotime(date('Y-m-d', strtotime("monday this week - {$i} weeks")))) . "-" . date('d/m', strtotime(date('Y-m-d', strtotime("sunday this week - {$i} weeks")))) . '</a></li>';
                        }
                        ?>

                        <?php if ($_GET["week"] < 49) { ?>
                            <li class="page-item disabled"><a class="page-link">...</a></li>
                        <?php } ?>

                        <li class="page-item <?php if ($_GET["week"] == 51) {
                            echo "active";
                        } ?>"><a class="page-link" href="?userID=<?php echo $_GET["userID"]; ?>&week=51">
                                <?php echo $translationsUsersUser['user_activities_zone_date_oneYearAgo']; ?>
                            </a></li>
                    </ul>
                </nav>
                <!-- week range text -->
                <p class="text-center">
                    <?php echo $translationsUsersUser['user_activities_zone_dateRange1']; ?>
                    <?php echo $formattedFirstDay; ?>
                    <?php echo $translationsUsersUser['user_activities_zone_dateRange2']; ?>
                    <?php echo $formattedLastDay; ?>
                </p>

                <?php if (!isset($weekActivities) || count($weekActivities) == 0) { ?>
                    <div class="centered-card">
                        <div class="card text-center">
                            <div class="card-body">
                                <h5 class="card-title">
                                    <?php echo $translationsUsersUser['user_activities_zone_ops']; ?>
                                </h5>
                                <h1 class="card-text"><i class="fa-solid fa-circle-info"></i></h1>
                                <p class="card-text">
                                    <?php echo $translationsUsersUser['user_activities_zone_noActivitiesFound']; ?>
                                </p>
                            </div>
                        </div>
                    </div>
                <?php } else { ?>
                    <?php foreach ($weekActivities as $activity) { ?>
                        <?php $activityStream = getActivityActivitiesStreamByStreamType($activity["id"],7);
                        if (isset($activityStream)){
                            if($activityStream["stream_type"] == 7){
                                $latlonStream = $activityStream["stream_waypoints"];
                            }
                        }else{
                            $latlonStream = null;
                        }
                        ?>
                        <div class="card">
                            <div class="card-body">
                                <div class="d-flex align-items-center">
                                    <div class="me-3">
                                        <div class="fw-bold">
                                            <a href="../activities/activity.php?activityID=<?php echo ($activity["id"]); ?>"
                                                class="link-underline-opacity-25 link-underline-opacity-100-hover">
                                                <?php echo ($activity["name"]); ?>
                                            </a>
                                        </div>
                                        <h7>
                                            <?php if ($activity["activity_type"] == 1 || $activity["activity_type"] == 2) {
                                                echo '<i class="fa-solid fa-person-running"></i>';
                                            } else {
                                                if ($activity["activity_type"] == 3) {
                                                echo '<i class="fa-solid fa-person-running"></i> (Virtual)';
                                                } else {
                                                    if ($activity["activity_type"] == 4 || $activity["activity_type"] == 5 || $activity["activity_type"] == 6) {
                                                        echo '<i class="fa-solid fa-person-biking"></i>';
                                                    } else {
                                                        if ($activity["activity_type"] == 7) {
                                                        echo '<i class="fa-solid fa-person-biking"></i> (Virtual)';
                                                            } else {
                                                            if ($activity["activity_type"] == 8 || $activity["activity_type"] == 9) {
                                                                echo '<i class="fa-solid fa-person-swimming"></i>';
                                                            } else {
                                                                if ($activity["activity_type"] == 10) {
                                                                echo '<i class="fa-solid fa-dumbbell"></i>';
                                                                }
                                                            }
                                                        }
                                                    }
                                                }
                                            } ?>
                                            <?php echo (new DateTime($activity["start_time"]))->format("d/m/y"); ?>@
                                            <?php echo (new DateTime($activity["start_time"]))->format("H:i"); ?>
                                            <?php if (isset($activity["city"]) || isset($activity["country"])) {
                                                echo " - ";
                                            } ?>
                                            <?php if (isset($activity["city"]) && !empty($activity["city"])) {
                                                echo $activity["city"] . ", ";
                                            } ?>
                                            <?php if (isset($activity["country"]) && !empty($activity["country"])) {
                                                echo $activity["country"];
                                            } ?>
                                        </h7>
                                    </div>
                                </div>
                                <div class="row d-flex mt-3">
                                    <div class="col">
                                        <span class="fw-lighter">
                                            <?php echo $translationsUsersUser['user_activities_zone_detail_distance']; ?>
                                        </span>
                                        <br>
                                        <?php if ($activity["activity_type"] != 9) { ?>
                                            <?php echo number_format(($activity["distance"] / 1000), 2); ?> km
                                        <?php } else { ?>
                                            <?php echo ($activity["distance"]); ?> m
                                        <?php } ?>
                                    </div>
                                    <div class="col border-start border-opacity-50">
                                        <span class="fw-lighter">
                                            <?php echo $translationsUsersUser['user_activities_zone_detail_time']; ?>
                                        </span>
                                        <br>
                                        <?php
                                        #echo $activity["start_time"];
                                        #echo $activity["end_time"];
                                        $startDateTime = new DateTime($activity["start_time"]);
                                        $endDateTime = new DateTime($activity["end_time"]);
                                        $interval = $startDateTime->diff($endDateTime);

                                        if ($interval->h < 1) {
                                            // If the difference is less than one hour
                                            echo $interval->i . "m " . $interval->s . "s";
                                        } else {
                                            // If the difference is one hour or more
                                            echo $interval->h . "h " . $interval->i . "m";
                                        }
                                        ?>
                                    </div>
                                    <div class="col border-start border-opacity-50">
                                        <?php if ($activity["activity_type"] != 9 && $activity["activity_type"] != 1) { ?>
                                            <span class="fw-lighter">
                                                <?php echo $translationsUsersUser['user_activities_zone_detail_elevation_gain']; ?>
                                            </span>
                                            <br>
                                            <?php echo ($activity["elevation_gain"]); ?> m
                                        <?php } else { ?>
                                            <?php if ($activity["activity_type"] == 1 || $activity["activity_type"] == 2 || $activity["activity_type"] == 3) { ?>
                                                <span class="fw-lighter">
                                                    <?php echo $translationsUsersUser['user_activities_zone_detail_pace']; ?>
                                                </span>
                                                <br>
                                                <?php echo floor(($activity["pace"] * 1000) / 60) . ":" . number_format((((($activity["pace"] * 1000) / 60) - floor(($activity["pace"] * 1000) / 60)) * 60), 0); ?>
                                                min/km
                                            <?php } else { ?>
                                                <?php if ($activity["activity_type"] == 9) { ?>
                                                    <span class="fw-lighter">
                                                        <?php echo $translationsUsersUser['user_activities_zone_detail_pace']; ?>
                                                    </span>
                                                    <br>
                                                    <?php echo floor(($activity["pace"] * 100) / 60) . ":" . number_format((((($activity["pace"] * 100) / 60) - floor(($activity["pace"] * 100) / 60)) * 60), 0); ?>
                                                    min/km
                                                <?php } ?>
                                            <?php } ?>
                                        <?php } ?>
                                    </div>
                                </div>
                            </div>
                            <?php if (isset($latlonStream)) { ?>
                                <div class="ms-3 me-3 <?php if ($activity['strava_activity_id'] == null) {
                                    echo "mb-3";
                                } ?>" id="map_<?php echo $activity['id']; ?>" style="height: 300px"></div>
                            <?php } ?>
                            <?php if ($activity['strava_activity_id'] != null) { ?>
                                <div class="mb-3">
                                    <span class="fw-lighter ms-3 me-3">
                                        <?php echo $translationsUsersUser['user_activities_zone_stravaText1']; ?><a
                                            href="https://www.strava.com/activities/<?php echo $activity['strava_activity_id']; ?>"
                                            target="_blank" rel="noopener noreferrer">
                                            <?php echo $translationsUsersUser['user_activities_zone_stravaText2']; ?>
                                        </a>
                                    </span>
                                </div>
                            <?php } ?>
                        </div>
                        <br>
                        <script>
                            // JavaScript code to create the map for this activity
                            var waypoints = <?php echo json_encode($latlonStream); ?>;
                            var mapId = "map_<?php echo $activity['id']; ?>";

                            var map = L.map(mapId, {
                                dragging: false, // Disable panning
                                touchZoom: false, // Disable touch zoom
                                scrollWheelZoom: false, // Disable scroll wheel zoom
                                zoomControl: false // Remove zoom control buttons
                            });

                            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                                maxZoom: 19,
                            }).addTo(map);

                            var latlngs = waypoints.map(function (waypoint) {
                                return [waypoint.lat, waypoint.lon];
                            });

                            L.polyline(latlngs, {
                                color: 'blue'
                            }).addTo(map);

                            // Calculate the bounds of the polyline and fit the map to those bounds
                            var bounds = L.latLngBounds(latlngs);
                            map.fitBounds(bounds);

                            // Add green dot for the first waypoint
                            L.marker([waypoints[0].lat, waypoints[0].lon], {
                                icon: L.divIcon({
                                    className: 'bg-success dot'
                                })
                            }).addTo(map);

                            // Add red dot for the last waypoint
                            L.marker([waypoints[waypoints.length - 1].lat, waypoints[waypoints.length - 1].lon], {
                                icon: L.divIcon({
                                    className: 'bg-danger dot'
                                })
                            }).addTo(map);
                        </script>
                    <?php } ?>
                <?php } ?>
            </div>
            <!-- div following -->
            <div class="tab-pane fade" id="pills-following" role="tabpanel" aria-labelledby="pills-following-tab"
                tabindex="0">
                <?php if (!$userFollowersCountAll) { ?>
                    <div class="centered-card">
                        <div class="card text-center">
                            <div class="card-body">
                                <h1 class="card-text"><i class="fa-solid fa-circle-info"></i></h1>
                                <p class="card-text">
                                    <?php echo $translationsUsersUser['user_following_zone_noFollowing']; ?>
                                </p>
                            </div>
                        </div>
                    </div>
                <?php } else { ?>
                    <ul class="list-group list-group-flush align-items-center">
                        <?php foreach ($userFollowingAll as $following) { ?>
                            <?php $userFollowing = getUserFromId($following["following_id"]); ?>
                            <li class="list-group-item d-flex justify-content-between">
                                <div class="d-flex align-items-center">
                                    <img src=<?php if (is_null($userFollowing["photo_path"])) {
                                        if ($userFollowing["gender"] == 1) {
                                            echo ("../img/avatar/male1.png");
                                        } else {
                                            echo ("../img/avatar/female1.png");
                                        }
                                    } else {
                                        echo ($userFollowing["photo_path"]);
                                    } ?> alt="userPicture" class="rounded-circle" width="55" height="55">
                                    <div class="ms-3">
                                        <div class="fw-bold">
                                            <a href="../users/user.php?userID=<?php echo ($userFollowing["id"]); ?>">
                                                <?php echo ($userFollowing["name"]); ?>
                                            </a>
                                        </div>
                                        <?php echo ($userFollowing["username"]); ?>
                                    </div>
                                </div>
                                <div class="ms-3 align-middle">
                                    <?php if ($following["is_accepted"] == 1) { ?>
                                        <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle"><?php echo $translationsUsersUser['user_following_zone_requestAccepted']; ?></span>
                                    <?php } else { ?>
                                        <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle"><?php echo $translationsUsersUser['user_following_zone_requestPending']; ?></span>
                                    <?php } ?>

                                    <?php if ($_GET["userID"] == $_SESSION["id"]) { ?>
                                        <!-- delete following button -->
                                        <a class="ms-2 btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteFollowingModal<?php echo ($userFollowing["id"]); ?>"><i class="fa-solid fa-trash"></i></a>

                                        <!-- Modal delete following -->
                                        <div class="modal fade" id="deleteFollowingModal<?php echo ($userFollowing["id"]); ?>" tabindex="-1" aria-labelledby="deleteFollowingModal<?php echo ($userFollowing["id"]); ?>"
                                            aria-hidden="true">
                                            <div class="modal-dialog">
                                                <div class="modal-content">
                                                    <div class="modal-header">
                                                        <h1 class="modal-title fs-5" id="deleteFollowingModal<?php echo ($userFollowing["id"]); ?>">
                                                            <?php echo $translationsUsersUser['user_deleteFollowing_modal_title']; ?>
                                                        </h1>
                                                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                                    </div>
                                                    <div class="modal-body">
                                                        <?php echo $translationsUsersUser['user_deleteFollowing_modal_body']; ?> <b>
                                                            <?php echo $userFollowing["name"]; ?>
                                                        </b>?
                                                    </div>
                                                    <div class="modal-footer">
                                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                                            <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                                        </button>
                                                        <a type="button" class="btn btn-danger"
                                                            href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&targetUserID=<?php echo ($userFollowing["id"]); ?>&deleteFollowing=1">
                                                            <?php echo $translationsUsersUser['user_deleteFollowing_modal_title']; ?>
                                                        </a>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    <?php } ?>
                                </div>
                            </li>
                        <?php } ?>
                    </ul>
                <?php } ?>
            </div>
            <!-- div followers -->
            <div class="tab-pane fade" id="pills-followers" role="tabpanel" aria-labelledby="pills-followers-tab"
                tabindex="0">
                <?php if (!$userFollowingCountAll) { ?>
                    <div class="centered-card">
                        <div class="card text-center">
                            <div class="card-body">
                                <h1 class="card-text"><i class="fa-solid fa-circle-info"></i></h1>
                                <p class="card-text">
                                    <?php echo $translationsUsersUser['user_following_zone_noFollowers']; ?>
                                </p>
                            </div>
                        </div>
                    </div>
                <?php } else { ?>
                    <ul class="list-group list-group-flush align-items-center">
                        <?php foreach ($userFollowersAll as $follower) { ?>
                            <?php $userFollower = getUserFromId($follower["follower_id"]); ?>
                            <li class="list-group-item d-flex justify-content-between">
                                <div class="d-flex align-items-center">
                                    <img src=<?php if (is_null($userFollower["photo_path"])) {
                                        if ($userFollower["gender"] == 1) {
                                            echo ("../img/avatar/male1.png");
                                        } else {
                                            echo ("../img/avatar/female1.png");
                                        }
                                    } else {
                                        echo ($userFollower["photo_path"]);
                                    } ?> alt="userPicture" class="rounded-circle" width="55" height="55">
                                    <div class="ms-3">
                                        <div class="fw-bold">
                                            <a href="../users/user.php?userID=<?php echo ($userFollower["id"]); ?>">
                                                <?php echo ($userFollower["name"]); ?>
                                            </a>
                                        </div>
                                        <?php echo ($userFollower["username"]); ?>
                                    </div>
                                </div>
                                <div class="ms-3 align-middle">
                                    <?php if ($follower["is_accepted"] == 1) { ?>
                                        <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle"><?php echo $translationsUsersUser['user_following_zone_requestAccepted']; ?></span>

                                        <?php if ($_GET["userID"] == $_SESSION["id"]) { ?>
                                            <!-- delete follower button -->
                                            <a class="ms-2 btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteFollowerModal<?php echo ($userFollower["id"]); ?>"><i class="fa-solid fa-trash"></i></a>

                                            <!-- Modal delete follower -->
                                            <div class="modal fade" id="deleteFollowerModal<?php echo ($userFollower["id"]); ?>" tabindex="-1" aria-labelledby="deleteFollowerModal<?php echo ($userFollower["id"]); ?>"
                                                aria-hidden="true">
                                                <div class="modal-dialog">
                                                    <div class="modal-content">
                                                        <div class="modal-header">
                                                            <h1 class="modal-title fs-5" id="deleteFollowerModal<?php echo ($userFollower["id"]); ?>">
                                                                <?php echo $translationsUsersUser['user_deleteFollower_modal_title']; ?>
                                                            </h1>
                                                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                                        </div>
                                                        <div class="modal-body">
                                                            <?php echo $translationsUsersUser['user_deleteFollower_modal_body']; ?> <b>
                                                                <?php echo $userFollower["name"]; ?>
                                                            </b>?
                                                        </div>
                                                        <div class="modal-footer">
                                                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                                                <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                                            </button>
                                                            <a type="button" class="btn btn-danger"
                                                                href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&targetUserID=<?php echo ($userFollower["id"]); ?>&deleteFollower=1">
                                                                <?php echo $translationsUsersUser['user_deleteFollower_modal_title']; ?>
                                                            </a>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        <?php } ?>
                                    <?php } else { ?>
                                        <?php if ($_GET["userID"] == $_SESSION["id"]) { ?>
                                            <!-- accept user request button -->
                                            <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#acceptRequestModal<?php echo ($userFollower["id"]); ?>"><i class="fa-solid fa-check"></i></a>

                                            <!-- Modal accept user request -->
                                            <div class="modal fade" id="acceptRequestModal<?php echo ($userFollower["id"]); ?>" tabindex="-1" aria-labelledby="acceptRequestModal<?php echo ($userFollower["id"]); ?>"
                                                aria-hidden="true">
                                                <div class="modal-dialog">
                                                    <div class="modal-content">
                                                        <div class="modal-header">
                                                            <h1 class="modal-title fs-5" id="acceptRequestModal<?php echo ($userFollower["id"]); ?>">
                                                                <?php echo $translationsUsersUser['user_acceptUserRequest_modal_title']; ?>
                                                            </h1>
                                                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                                        </div>
                                                        <div class="modal-body">
                                                            <?php echo $translationsUsersUser['user_acceptUserRequest_modal_body']; ?> <b>
                                                                <?php echo $userFollower["name"]; ?>
                                                            </b>?
                                                        </div>
                                                        <div class="modal-footer">
                                                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                                                <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                                            </button>
                                                            <a type="button" class="btn btn-success"
                                                                href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&targetUserID=<?php echo ($userFollower["id"]); ?>&acceptUserRequest=1">
                                                                <?php echo $translationsUsersUser['user_acceptUserRequest_modal_title']; ?>
                                                            </a>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>

                                            <!-- decline user request button -->
                                            <a class="ms-2 btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#declineRequestModal<?php echo ($userFollower["id"]); ?>"><i class="fa-solid fa-x"></i></a>

                                            <!-- Modal decline user request -->
                                            <div class="modal fade" id="declineRequestModal<?php echo ($userFollower["id"]); ?>" tabindex="-1" aria-labelledby="declineRequestModal<?php echo ($userFollower["id"]); ?>"
                                                aria-hidden="true">
                                                <div class="modal-dialog">
                                                    <div class="modal-content">
                                                        <div class="modal-header">
                                                            <h1 class="modal-title fs-5" id="declineRequestModal<?php echo ($userFollower["id"]); ?>">
                                                                <?php echo $translationsUsersUser['user_declineUserRequest_modal_title']; ?>
                                                            </h1>
                                                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                                        </div>
                                                        <div class="modal-body">
                                                            <?php echo $translationsUsersUser['user_declineUserRequest_modal_body']; ?> <b>
                                                                <?php echo $userFollower["name"]; ?>
                                                            </b>?
                                                        </div>
                                                        <div class="modal-footer">
                                                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                                                <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                                            </button>
                                                            <a type="button" class="btn btn-danger"
                                                                href="../users/user.php?userID=<?php echo ($_GET["userID"]); ?>&targetUserID=<?php echo ($userFollower["id"]); ?>&declineUserRequest=1">
                                                                <?php echo $translationsUsersUser['user_declineUserRequest_modal_title']; ?>
                                                            </a>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        <?php }else{ ?>
                                            <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle"><?php echo $translationsUsersUser['user_following_zone_requestPending']; ?></span>
                                        <?php } ?>
                                    <?php } ?>
                                </div>
                            </li>
                        <?php } ?>
                    </ul>
                <?php } ?>
            </div>
        </div>

    </div>
    <div>
        <br class="d-lg-none">
        <button onclick="window.history.back();" type="button" class="w-100 btn btn-primary d-lg-none">
            <?php echo $translationsTemplateTop['template_top_global_back']; ?>
        </button>
    </div>
</div>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>