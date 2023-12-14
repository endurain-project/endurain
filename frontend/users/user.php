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

// if userID not set redirect to index.php
if(!isset($_GET["userID"])){
    header("Location: ../index.php");
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
$numUserActivitiesThisMonth = getUserActivitiesThisMonthNumber($_GET["userID"]);

if(!isset($_GET["week"])){
    $_GET["week"] = 0;
}

$weekActivities = getUserActivitiesWeek($_GET["userID"], $_GET["week"]);

// Default week offset is 0 (current week)
$weekOffset = isset($_GET["week"]) ? intval($_GET["week"]) : 0;

// Calculate the first day of the desired week
$firstDay = date('Y-m-d', strtotime("monday this week - {$weekOffset} weeks"));

// Calculate the last day of the desired week
$lastDay = date('Y-m-d', strtotime("sunday this week - {$weekOffset} weeks"));

// Format the dates as desired (day month year)
$formattedFirstDay = date('d F Y', strtotime($firstDay));
$formattedLastDay = date('d F Y', strtotime($lastDay));

?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<div class="container mt-4">
    <div class="row align-items-center">
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
                    } ?> alt="userPicture" class="rounded-circle" width="120"
                        height="120">
                </div>
                <div class="text-center mt-3 mb-3">
                    <h3><?php echo $user[0]["name"]; ?></h3>
                    <?php if(isset($user[0]["city"])){ ?>
                        <span class="fw-lighter">
                            <i class="fa-solid fa-location-dot"></i> <?php echo $user[0]["city"]; ?>
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
                <h1><?php echo $numUserActivitiesThisMonth["activity_count"]; ?></h1>
                <hr class="mb-2 mt-2">
                <div class="row align-items-center">
                    <div class="col">
                        0
                        <br>
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_main_nav_following']; ?>
                        </span>
                    </div>
                    <div class="col">
                        0
                        <br>
                        <span class="fw-lighter">
                            <?php echo $translationsUsersUser['user_main_nav_followers']; ?>
                        </span>
                    </div>
                </div>
            </div>
        </div>
        <div class="col-sm">

        </div>
    </div>
    
    <!--<div class="row">
        <div class="col-sm-4">
            col-sm-8
        </div>
        <div class="col-sm-8">
            col-sm-4
        </div>
    </div>-->
    <!-- main -->

    <!-- navbar for user page -->
    <div>
        <ul class="nav nav-pills mb-3 justify-content-center" id="pills-tab" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="pills-activities-tab" data-bs-toggle="pill" data-bs-target="#pills-activities" type="button" role="tab" aria-controls="pills-activities" aria-selected="true"><?php echo $translationsUsersUser['user_main_nav_activities']; ?></button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="pills-following-tab" data-bs-toggle="pill" data-bs-target="#pills-following" type="button" role="tab" aria-controls="pills-following" aria-selected="false"><?php echo $translationsUsersUser['user_main_nav_following']; ?></button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="pills-followers-tab" data-bs-toggle="pill" data-bs-target="#pills-followers" type="button" role="tab" aria-controls="pills-followers" aria-selected="false"><?php echo $translationsUsersUser['user_main_nav_followers']; ?></button>
            </li>
            <?php if($_GET["userID"] == $_SESSION["id"]){ ?>
                <li class="nav-item" role="presentation">
                    <a class="btn nav-link" href="../settings/settings.php?profileSettings=1"><i class="fa-solid fa-gear"></i> <?php echo $translationsUsersUser['user_main_nav_user_settings']; ?></a>
                </li>
            <?php } ?>
        </ul>
        <div class="tab-content" id="pills-tabContent">
            <!-- div activities -->
            <div class="tab-pane fade show active" id="pills-activities" role="tabpanel" aria-labelledby="pills-activities-tab" tabindex="0">
                <!-- pagination -->
                <nav>
                    <ul class="pagination justify-content-center">
                        <li class="page-item <?php if ($_GET["week"] == 0) {
                            echo "active";
                        } ?>"><a class="page-link" href="?userID=<?php echo $_GET["userID"] ;?>&week=0">0</a></li>

                        <?php if($_GET["week"] > 2) { ?>
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
                            echo '"><a class="page-link" href="?userID=' . $_GET["userID"] . '&week=' . $i . '">' . $i . '</a></li>';
                        }
                        ?>

                        <?php if($_GET["week"] < 49) { ?>
                            <li class="page-item disabled"><a class="page-link">...</a></li>
                        <?php } ?>

                        <li class="page-item <?php if ($_GET["week"] == 51) {
                            echo "active";
                        } ?>"><a class="page-link" href="?userID=<?php echo $_GET["userID"] ;?>&week=51">51</a></li>
                    </ul>
                </nav>
                <!-- week range text -->
                <p class="text-center"><?php echo $translationsUsersUser['user_activities_zone_dateRange1']; ?><?php echo $formattedFirstDay; ?><?php echo $translationsUsersUser['user_activities_zone_dateRange2']; ?><?php echo $formattedLastDay; ?></p>

                <?php foreach ($weekActivities as $activity) { ?>
                    <div class="card">
                        <div class="card-body">
                        <div class="d-flex align-items-center">
                            <div class="me-3">
                                <div class="fw-bold">
                                    <a href="activities/activity.php?activityID=<?php echo ($activity["id"]); ?>"
                                    class="link-underline-opacity-25 link-underline-opacity-100-hover">
                                    <?php echo ($activity["name"]); ?>
                                    </a>
                                </div>
                                <h7>
                                    <?php if ($activity["activity_type"] == 1) {
                                    echo '<i class="fa-solid fa-person-running"></i>';
                                    } else {
                                    if ($activity["activity_type"] == 4 || $activity["activity_type"] == 5 || $activity["activity_type"] == 6 || $activity["activity_type"] == 8) {
                                        echo '<i class="fa-solid fa-person-biking"></i>';
                                    } else {
                                        if ($activity["activity_type"] == 7) {
                                        echo '<i class="fa-solid fa-person-biking"></i> (Virtual)';
                                        } else {
                                        if ($activity["activity_type"] == 9) {
                                            echo '<i class="fa-solid fa-person-swimming"></i>';
                                        } else {
                                            if ($activity["activity_type"] == 10) {
                                            echo '<i class="fa-solid fa-dumbbell"></i>';
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
                                $startDateTime = DateTime::createFromFormat("Y-m-d\TH:i:s", $activity["start_time"]);
                                $endDateTime = DateTime::createFromFormat("Y-m-d\TH:i:s", $activity["end_time"]);
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
                        <?php if (isset($activity["waypoints"][0]["lat"])) { ?>
                        <div class="ms-3 me-3 <?php if ($activity['strava_activity_id'] == null) {
                            echo "mb-3";
                        } ?>" id="map_<?php echo $activity['id']; ?>" style="height: 300px"></div>
                        <?php } ?>
                        <?php if ($activity['strava_activity_id'] != null) { ?>
                        <div class="mb-3">
                            <span class="fw-lighter ms-3 me-3">
                            <?php echo $translationsUsersUser['user_activities_zone_stravaText1']; ?><a
                                href="https://www.strava.com/activities/<?php echo $activity['strava_activity_id']; ?>" target="_blank"
                                rel="noopener noreferrer">
                                <?php echo $translationsUsersUser['user_activities_zone_stravaText2']; ?>
                            </a>
                            </span>
                        </div>
                        <?php } ?>
                    </div>
                    <br>
                    <script>
                        // JavaScript code to create the map for this activity
                        var waypoints = <?php echo json_encode($activity['waypoints']); ?>;
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
            </div>
            <!-- div following -->
            <div class="tab-pane fade" id="pills-following" role="tabpanel" aria-labelledby="pills-following-tab" tabindex="0">

            </div>
            <!-- div followers -->
            <div class="tab-pane fade" id="pills-followers" role="tabpanel" aria-labelledby="pills-followers-tab" tabindex="0">
                
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