<?php
if (!isset($_SESSION)) {
    session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "activity";
$activity = [];
$addGearToActivity = -9000;
$editGearActivity = -9000;
$deleteGearActivity = -9000;
$deleteActivity = -9000;

if (!isLogged()) {
    header("Location: ../login.php");
}

if (!isTokenValid($_SESSION["token"])) {
    header("Location: ../logout.php?sessionExpired=1");
}

if (!isset($_GET["activityID"])) {
    header("Location: ../index.php?invalidActivity=1");
}

// Load the language file based on the user's preferred language
switch ($_SESSION["preferred_language"]) {
    case 'en':
        $translationsActivitiesActivity = include $_SERVER['DOCUMENT_ROOT'] . '/lang/activities/en.php';
        break;
    case 'pt':
        $translationsActivitiesActivity = include $_SERVER['DOCUMENT_ROOT'] . '/lang/activities/pt.php';
        break;
    // ...
    default:
        $translationsActivitiesActivity = include $_SERVER['DOCUMENT_ROOT'] . '/lang/activities/en.php';
}

/* Add gear to activity action */
if (isset($_GET["addGearToActivity"]) && $_GET["addGearToActivity"] == 1) {
    $addGearToActivity = addGearToActivity($_GET["activityID"], $_POST["gearIDAdd"]);
}

/* Edit activity gear */
if (isset($_GET["editGearActivity"]) && $_GET["editGearActivity"] == 1) {
    $editGearActivity = addGearToActivity($_GET["activityID"], $_POST["gearIDEdit"]);
}

/* Delete activity gear */
if (isset($_GET["deleteGearActivity"]) && $_GET["deleteGearActivity"] == 1) {
    $deleteGearActivity = unsetActivityGear($_GET["activityID"]);
}

/* Delete activity */
if (isset($_GET["deleteActivity"]) && $_GET["deleteActivity"] == 1) {
    $deleteActivity = deleteActivity($_GET["activityID"]);
    if ($deleteActivity == 0) {
        header("Location: ../index.php?deleteActivity=1");
    }
}

$activity = getActivityFromId($_GET["activityID"]);
if ($activity == NULL) {
    header("Location: ../index.php?invalidActivity=1");
}

$activityStreams = getActivityActivitiesStream($activity[0]["id"]); 
$hrStream = [];
$cadStream = [];
$powerStream = [];
$eleStream = [];
$velStream = [];
$paceStream = [];
foreach ($activityStreams as $stream) {
    if($stream["stream_type"] == 1){
        $hrStream = $stream["stream_waypoints"];
    }
    if($stream["stream_type"] == 2){
        $powerStream = $stream["stream_waypoints"];
    }
    if($stream["stream_type"] == 3){
        $cadStream = $stream["stream_waypoints"];
    }
    if($stream["stream_type"] == 4){
        $eleStream = $stream["stream_waypoints"];
    }
    if($stream["stream_type"] == 5){
        #$velStream = $stream["stream_waypoints"];
        foreach($stream["stream_waypoints"] as $velData){
            $velStream[] = (float) number_format(($velData['vel'] * 3.6), 0);
        }
    }
    #if($stream["stream_type"] == 6){
    #    $paceStream = $stream["stream_waypoints"];
    #}
    if($stream["stream_type"] == 7){
        $latlonStream = $stream["stream_waypoints"];
    }
    #$velStream[] = (float) number_format(($waypoint['vel'] * 3.6), 0);
    if ($activity[0]["activity_type"] == 1 || $activity[0]["activity_type"] == 2 || $activity[0]["activity_type"] == 3) {
        if($stream["stream_type"] == 6){
            foreach($stream["stream_waypoints"] as $paceData){
                if ($paceData['pace'] == 0 || $paceData['pace'] == null) {
                    $paceStream[] = 0;
                } else {
                    $paceStream[] = ($paceData["pace"] * 1000) / 60;
                }
            }
        }
    } else {
        if ($activity[0]["activity_type"] == 9) {
            if($stream["stream_type"] == 6){
                foreach($stream["stream_waypoints"] as $paceData){
                    if ($paceData['pace'] == 0 || $paceData['pace'] == null) {
                        $paceStream[] = 0;
                    } else {
                        $paceStream[] = ($paceData["pace"] * 100) / 60;
                    }
                }
            }
        }
    }
}

$activityUser = getUserFromId($activity[0]['user_id']);

if ($activity[0]["gear_id"] != null) {
    $activityGear = getGearFromId($activity[0]["gear_id"]);
}

if ($activity[0]["activity_type"] == 1 || $activity[0]["activity_type"] == 2 || $activity[0]["activity_type"] == 3) {
    $activityGearOptions = getGearFromType(2);
} else {
    if ($activity[0]["activity_type"] == 4 || $activity[0]["activity_type"] == 5 || $activity[0]["activity_type"] == 6 || $activity[0]["activity_type"] == 7 || $activity[0]["activity_type"] == 8) {
        $activityGearOptions = getGearFromType(1);
    } else {
        if ($activity[0]["activity_type"] == 9) {
            $activityGearOptions = getGearFromType(3);
        }
    }
}
?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<div class="container mt-4">
    <!-- Error banners -->
    <?php if ($addGearToActivity == -1 || $addGearToActivity == -2 || $editGearActivity == -1 || $editGearActivity == -2 || $deleteGearActivity == -1 || $deleteGearActivity == -2 || $deleteActivity == -1 || $deleteActivity == -2) { ?>
        <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
            <i class="fa-solid fa-circle-exclamation me-1"></i>
            <div>
                <?php if ($addGearToActivity == -1 || $editGearActivity == -1 || $deleteActivity == -1) { ?>
                    API ERROR |
                    <?php echo $translationsActivitiesActivity['activity_addEditGear_API_error_-1']; ?> (-1).
                <?php } else { ?>
                    <?php if ($addGearToActivity == -2 || $editGearActivity == -2 || $deleteActivity == -2) { ?>
                        API ERROR |
                        <?php echo $translationsActivitiesActivity['activity_addEditGear_API_error_-2']; ?> (-2).
                    <?php } ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>

    <!-- Info banners -->

    <!-- Success banners -->
    <?php if ($addGearToActivity == 0 || $editGearActivity == 0 || $deleteGearActivity == 0) { ?>
        <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
            <div>
                <i class="fa-regular fa-circle-check me-1"></i>
                <?php if ($addGearToActivity == 0) { ?>
                    <?php echo $translationsActivitiesActivity['activity_success_gearAdded']; ?>
                <?php } else { ?>
                    <?php if ($editGearActivity == 0) { ?>
                        <?php echo $translationsActivitiesActivity['activity_success_gearEdited']; ?>
                    <?php } else { ?>
                        <?php if ($deleteGearActivity == 0) { ?>
                            <?php echo $translationsActivitiesActivity['activity_success_gearDeleted']; ?>
                        <?php } ?>
                    <?php } ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>


    <div class="d-flex justify-content-between">
        <!-- Activity user details -->
        <div class="d-flex align-items-center">
            <img src=<?php if (is_null($activityUser[0]["photo_path"])) {
                if ($activityUser[0]["gender"] == 1) {
                    echo ("../img/avatar/male1.png");
                } else {
                    echo ("../img/avatar/female1.png");
                }
            } else {
                echo ($activityUser[0]["photo_path"]);
            } ?> alt="userPicture" class="rounded-circle" width="55" height="55">
            <div class="ms-3 me-3">
                <div class="fw-bold">
                    <a href="../users/user.php?userID=<?php echo ($activityUser[0]["id"]); ?>">
                        <?php echo ($activityUser[0]["name"]); ?>
                    </a>
                </div>
                <!-- Activity time and place details -->
                <h7>
                    <?php if ($activity[0]["activity_type"] == 1) {
                        echo '<i class="fa-solid fa-person-running"></i>';
                    } else {
                        if ($activity[0]["activity_type"] == 4 || $activity[0]["activity_type"] == 5 || $activity[0]["activity_type"] == 6 || $activity[0]["activity_type"] == 7 || $activity[0]["activity_type"] == 8) {
                            echo '<i class="fa-solid fa-person-biking"></i>';
                        } else {
                            if ($activity[0]["activity_type"] == 9) {
                                echo '<i class="fa-solid fa-person-swimming"></i>';
                            }
                        }
                    } ?>
                    <?php echo (new DateTime($activity[0]["start_time"]))->format("d/m/y"); ?>@
                    <?php echo (new DateTime($activity[0]["start_time"]))->format("H:i"); ?>
                    <?php if (isset($activity[0]["city"]) || isset($activity[0]["country"])) {
                        echo " - ";
                    } ?>
                    <?php if (isset($activity[0]["city"]) && !empty($activity[0]["city"])) {
                        echo $activity[0]["city"] . ", ";
                    } ?>
                    <?php if (isset($activity[0]["country"]) && !empty($activity[0]["country"])) {
                        echo $activity[0]["country"];
                    } ?>
                </h7>
            </div>
        </div>
        <div class="dropdown d-flex">
            <button class="btn btn-link btn-lg" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                <i class="fa-solid fa-ellipsis-vertical"></i>
            </button>
            <ul class="dropdown-menu">
                <?php if ($activity[0]['strava_activity_id'] != null) { ?>
                    <li><a class="dropdown-item"
                            href="https://www.strava.com/activities/<?php echo $activity[0]['strava_activity_id']; ?>">
                            <?php echo $translationsActivitiesActivity['activity_title_dropdown_seeItOnStrava']; ?>
                        </a></li>
                <?php } ?>
                <li><a class="dropdown-item" href="#" data-bs-toggle="modal" data-bs-target="#deleteActivityModal">
                        <?php echo $translationsActivitiesActivity['activity_title_dropdown_deleteActivity']; ?>
                    </a></li>
            </ul>
        </div>
    </div>

    <!-- Modal delete gear -->
    <div class="modal fade" id="deleteActivityModal" tabindex="-1" aria-labelledby="deleteActivityModal"
        aria-hidden="true">
        <div class="modal-dialog">
            <div class="modal-content">
                <div class="modal-header">
                    <h1 class="modal-title fs-5" id="deleteActivityModal">
                        <?php echo $translationsActivitiesActivity['activity_title_dropdown_deleteActivity']; ?>
                    </h1>
                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <?php echo $translationsActivitiesActivity['activity_title_dropdown_deleteActivity_modal_body']; ?>
                    <b>
                        <?php echo $activity[0]['name']; ?>
                    </b>?
                </div>
                <div class="modal-footer">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                        <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                    </button>
                    <a type="button" class="btn btn-danger"
                        href="../activities/activity.php?activityID=<?php echo $activity[0]["id"]; ?>&deleteActivity=1">
                        <?php echo $translationsActivitiesActivity['activity_title_dropdown_deleteActivity']; ?>
                    </a>
                </div>
            </div>
        </div>
    </div>

    <!-- Activity title -->
    <h1 class="mt-3">
        <?php echo $activity[0]["name"]; ?>
    </h1>

    <!-- Details -->
    <div class=" row d-flex mt-3">
        <div class="col">
            <span class="fw-lighter">
                <?php echo $translationsActivitiesActivity['activity_detail_distance']; ?>
            </span>
            <br>
            <?php if ($activity[0]["activity_type"] != 9) { ?>
                <?php echo number_format(($activity[0]["distance"] / 1000), 2); ?> km
            <?php } else { ?>
                <?php echo ($activity[0]["distance"]); ?> m
            <?php } ?>
        </div>
        <div class="col border-start border-opacity-50">
            <span class="fw-lighter">
                <?php echo $translationsActivitiesActivity['activity_detail_time']; ?>
            </span>
            <br>
            <?php
            $startDateTime = DateTime::createFromFormat("Y-m-d\TH:i:s", $activity[0]["start_time"]);
            $endDateTime = DateTime::createFromFormat("Y-m-d\TH:i:s", $activity[0]["end_time"]);
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
            <?php if ($activity[0]["activity_type"] != 9 && $activity[0]["activity_type"] != 1) { ?>
                <span class="fw-lighter">
                    <?php echo $translationsActivitiesActivity['activity_detail_elevationGain']; ?>
                </span>
                <br>
                <?php echo ($activity[0]["elevation_gain"]); ?> m
            <?php } else { ?>
                <?php if ($activity[0]["activity_type"] == 1 || $activity[0]["activity_type"] == 2 || $activity[0]["activity_type"] == 3) { ?>
                    <span class="fw-lighter">
                        <?php echo $translationsActivitiesActivity['activity_detail_pace']; ?>
                    </span>
                    <br>
                    <?php echo floor(($activity[0]["pace"] * 1000) / 60) . ":" . number_format((((($activity[0]["pace"] * 1000) / 60) - floor(($activity[0]["pace"] * 1000) / 60)) * 60), 0); ?>
                    min/km
                <?php } else { ?>
                    <?php if ($activity[0]["activity_type"] == 9) { ?>
                        <span class="fw-lighter">
                            <?php echo $translationsActivitiesActivity['activity_detail_pace']; ?>
                        </span>
                        <br>
                        <?php echo floor(($activity[0]["pace"] * 100) / 60) . ":" . number_format((((($activity[0]["pace"] * 100) / 60) - floor(($activity[0]["pace"] * 100) / 60)) * 60), 0); ?>
                        min/100m
                    <?php } ?>
                <?php } ?>
            <?php } ?>
        </div>
    </div>
    <!-- other metrics -->
    <div class="row d-flex mt-3">
        <?php if ($activity[0]["activity_type"] == 1 || $activity[0]["activity_type"] == 2 || $activity[0]["activity_type"] == 3) { ?>
            <div class="col">
                <span class="fw-lighter">
                    <?php echo $translationsActivitiesActivity['activity_detail_avgPower']; ?>
                </span>
                <br>
                <?php if ($activity[0]["average_power"]) {
                    echo ($activity[0]["average_power"]); ?> W
                <?php } else {
                    echo "No data";
                } ?>
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    <?php echo $translationsActivitiesActivity['activity_detail_elevationGain']; ?>
                </span>
                <br>
                <?php echo ($activity[0]["elevation_gain"]); ?> m
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    <?php echo $translationsActivitiesActivity['activity_detail_elevationLoss']; ?>
                </span>
                <br>
                <?php echo ($activity[0]["elevation_loss"]); ?> m
            </div>
        <?php } ?>
        <?php if ($activity[0]["activity_type"] != 9 && $activity[0]["activity_type"] != 1) { ?>
            <div class="col">
                <span class="fw-lighter">
                    <?php echo $translationsActivitiesActivity['activity_detail_avgSpeed']; ?>
                </span>
                <br>
                <?php echo (number_format($activity[0]["average_speed"] * 3.6)); ?> km/h
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    <?php echo $translationsActivitiesActivity['activity_detail_avgPower']; ?>
                </span>
                <br>
                <?php if ($activity[0]["average_power"]) {
                    echo ($activity[0]["average_power"]); ?> W
                <?php } else {
                    echo "No data";
                } ?>
            </div>
            <div class="col border-start border-opacity-50">
                <span class="fw-lighter">
                    <?php echo $translationsActivitiesActivity['activity_detail_elevationLoss']; ?>
                </span>
                <br>
                <?php echo $activity[0]["elevation_loss"]; ?> m
            </div>
        <?php } ?>
        <div>

            <!-- Map -->
            <?php if (isset($latlonStream)) { ?>
                <div class="mt-3 mb-3" id="map" style="height: 500px"></div>
            <?php } ?>


            <script>
                // JavaScript code to create the map for this activity
                var waypoints = <?php echo json_encode($latlonStream); ?>;
                var mapId = "map";

                var map = L.map(mapId, {
                    //dragging: false,   // Disable panning
                    //touchZoom: false,  // Disable touch zoom
                    //scrollWheelZoom: false, // Disable scroll wheel zoom
                    //zoomControl: false // Remove zoom control buttons
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

            <!-- gear  -->
            <hr class="mb-2 mt-2">
            <div class="d-flex justify-content-between align-items-center">
                <p class="pt-2">
                    <span class="fw-lighter">
                        <?php echo $translationsActivitiesActivity['activity_gear_title']; ?>
                    </span>
                    <br>
                    <?php if ($activity[0]["activity_type"] == 1) {
                        echo '<i class="fa-solid fa-person-running"></i>';
                    } else {
                        if ($activity[0]["activity_type"] == 4 || $activity[0]["activity_type"] == 5 || $activity[0]["activity_type"] == 6 || $activity[0]["activity_type"] == 7 || $activity[0]["activity_type"] == 8) {
                            echo '<i class="fa-solid fa-person-biking"></i>';
                        } else {
                            if ($activity[0]["activity_type"] == 9) {
                                echo '<i class="fa-solid fa-person-swimming"></i>';
                            }
                        }
                    } ?>
                    <?php if ($activity[0]["gear_id"] == null) { ?>
                        <?php echo $translationsActivitiesActivity['activity_gear_notset']; ?>
                    <?php } else { ?>
                        <?php echo $activityGear[0]['nickname']; ?>
                    <?php } ?>
                </p>
                <div class="justify-content-end">
                    <?php if ($activity[0]["gear_id"] == null) { ?>
                        <!-- add gear zone -->
                        <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal"
                            data-bs-target="#addGearToActivityModal"><i class="fa-solid fa-plus"></i></a>

                        <!-- modal -->
                        <div class="modal fade" id="addGearToActivityModal" tabindex="-1"
                            aria-labelledby="addGearToActivityModal" aria-hidden="true">
                            <div class="modal-dialog">
                                <div class="modal-content">
                                    <div class="modal-header">
                                        <h1 class="modal-title fs-5" id="addGearToActivityModal">
                                            <?php echo $translationsActivitiesActivity['activity_gear_addGear_title']; ?>
                                        </h1>
                                        <button type="button" class="btn-close" data-bs-dismiss="modal"
                                            aria-label="Close"></button>
                                    </div>
                                    <form
                                        action="../activities/activity.php?activityID=<?php echo $activity[0]["id"]; ?>&addGearToActivity=1"
                                        method="post" enctype="multipart/form-data">
                                        <div class="modal-body">
                                            <!-- gear type fields -->
                                            <label for="gearIDAdd"><b>*
                                                    <?php echo $translationsActivitiesActivity['activity_gear_addGear_label']; ?>
                                                </b></label>
                                            <select class="form-control" name="gearIDAdd">
                                                <?php foreach ($activityGearOptions as $option) { ?>
                                                    <option value="<?php echo $option["id"]; ?>">
                                                        <?php echo $option["nickname"]; ?>
                                                    </option>
                                                <?php } ?>
                                            </select required>
                                        </div>
                                        <div class="modal-footer">
                                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                                <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                            </button>
                                            <button type="submit" class="btn btn-success" name="addGearToActivity">
                                                <?php echo $translationsActivitiesActivity['activity_gear_addGear_submit']; ?>
                                            </button>
                                        </div>
                                    </form>
                                </div>
                            </div>
                        </div>
                    <?php } else { ?>
                        <!-- Edit zone -->
                        <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal"
                            data-bs-target="#editGearActivityModal"><i class="fa-regular fa-pen-to-square"></i></a>

                        <!-- modal -->
                        <div class="modal fade" id="editGearActivityModal" tabindex="-1"
                            aria-labelledby="editGearActivityModal" aria-hidden="true">
                            <div class="modal-dialog">
                                <div class="modal-content">
                                    <div class="modal-header">
                                        <h1 class="modal-title fs-5" id="editGearActivityModal">
                                            <?php echo $translationsActivitiesActivity['activity_gear_editGear_title']; ?>
                                        </h1>
                                        <button type="button" class="btn-close" data-bs-dismiss="modal"
                                            aria-label="Close"></button>
                                    </div>
                                    <form
                                        action="../activities/activity.php?activityID=<?php echo $activity[0]["id"]; ?>&editGearActivity=1"
                                        method="post" enctype="multipart/form-data">
                                        <div class="modal-body">
                                            <!-- gear type fields -->
                                            <label for="gearIDEdit"><b>*
                                                    <?php echo $translationsActivitiesActivity['activity_gear_addGear_label']; ?>
                                                </b></label>
                                            <select class="form-control" name="gearIDEdit">
                                                <?php foreach ($activityGearOptions as $option) { ?>
                                                    <option value="<?php echo $option["id"]; ?>">
                                                        <?php echo $option["nickname"]; ?>
                                                    </option>
                                                <?php } ?>
                                            </select required>
                                        </div>
                                        <div class="modal-footer">
                                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                                <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                            </button>
                                            <button type="submit" class="btn btn-success" name="editGearActivity">
                                                <?php echo $translationsActivitiesActivity['activity_gear_editGear_submit']; ?>
                                            </button>
                                        </div>
                                    </form>
                                </div>
                            </div>
                        </div>

                        <!-- Delete zone -->
                        <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal"
                            data-bs-target="#deleteGearActivityModal"><i class="fa-solid fa-trash"></i></a>

                        <!-- Modal delete gear -->
                        <div class="modal fade" id="deleteGearActivityModal" tabindex="-1"
                            aria-labelledby="deleteGearActivityModal" aria-hidden="true">
                            <div class="modal-dialog">
                                <div class="modal-content">
                                    <div class="modal-header">
                                        <h1 class="modal-title fs-5" id="deleteGearActivityModal">
                                            <?php echo $translationsActivitiesActivity['activity_gear_deleteGear_title']; ?>
                                        </h1>
                                        <button type="button" class="btn-close" data-bs-dismiss="modal"
                                            aria-label="Close"></button>
                                    </div>
                                    <div class="modal-body">
                                        <?php echo $translationsActivitiesActivity['activity_gear_deleteGear_body']; ?> <b>
                                            <?php echo $activityGear[0]['nickname']; ?>
                                        </b>?
                                    </div>
                                    <div class="modal-footer">
                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                            <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                        </button>
                                        <a type="button" class="btn btn-danger"
                                            href="../activities/activity.php?activityID=<?php echo $activity[0]["id"]; ?>&deleteGearActivity=1">
                                            <?php echo $translationsActivitiesActivity['activity_gear_deleteGear_title']; ?>
                                        </a>
                                    </div>
                                </div>
                            </div>
                        </div>
                    <?php } ?>
                </div>
            </div>

            <!-- waypoints graph -->
            <hr class="mb-2 mt-2">
            <div class="row">

                <!--<h2 class="mb-3"><?php echo $translationsActivitiesActivity['activity_dataGraph_title']; ?></h2>-->

                <div class="col-md-2">
                    <p>
                        <?php echo $translationsActivitiesActivity['activity_dataGraph_dataSelection']; ?>
                    </p>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="hrCheckbox" checked>
                        <label class="form-check-label" for="hrCheckbox">
                            <?php echo $translationsActivitiesActivity['activity_dataGraph_hr']; ?>
                        </label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="cadenceCheckbox">
                        <label class="form-check-label" for="cadenceCheckbox">
                            <?php echo $translationsActivitiesActivity['activity_dataGraph_cad']; ?>
                        </label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="powerCheckbox">
                        <label class="form-check-label" for="powerCheckbox">
                            <?php echo $translationsActivitiesActivity['activity_dataGraph_power']; ?>
                        </label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="elevationCheckbox">
                        <label class="form-check-label" for="elevationCheckbox">
                            <?php echo $translationsActivitiesActivity['activity_dataGraph_ele']; ?>
                        </label>
                    </div>
                    <?php if ($activity[0]["activity_type"] == 4 || $activity[0]["activity_type"] == 5 || $activity[0]["activity_type"] == 6 || $activity[0]["activity_type"] == 7 || $activity[0]["activity_type"] == 8) { ?>
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="velocityCheckbox">
                            <label class="form-check-label" for="velocityCheckbox">
                                <?php echo $translationsActivitiesActivity['activity_dataGraph_vel']; ?>
                            </label>
                        </div>
                    <?php } else { ?>
                        <div class="form-check">
                            <input class="form-check-input" type="checkbox" id="paceCheckbox">
                            <label class="form-check-label" for="paceCheckbox">
                                <?php echo $translationsActivitiesActivity['activity_dataGraph_pace']; ?>
                            </label>
                        </div>
                    <?php } ?>
                </div>
                <div class="col">
                    <canvas id="dataChart" height="100"></canvas>
                    <p class="fw-lighter">
                        <?php echo $translationsActivitiesActivity['activity_dataGraph_downsampleDataInfo']; ?>
                    </p>
                </div>
            </div>

            <script>
                var ctx = document.getElementById('dataChart').getContext('2d');
                var activityType = <?php echo $activity[0]["activity_type"]; ?>;

                const downsampledDataHr = downsampleData(<?php foreach($hrStream as $hrValue){ $auxhr[] = (int)$hrValue["hr"]; } echo json_encode($auxhr); ?>, 200);

                const downsampledDataCad = downsampleData(<?php foreach($cadStream as $cadValue){ $auxcad[] = (int)$cadValue["cad"]; } echo json_encode($auxcad); ?>, 200);

                const downsampledDataPower = downsampleData(<?php foreach($powerStream as $powerValue){ $auxpower[] = (int)$powerValue["power"]; } echo json_encode($auxpower); ?>, 200);

                const downsampledDataEle = downsampleData(<?php foreach($eleStream as $eleValue){ $auxele[] = (int)$eleValue["ele"]; } echo json_encode($auxele); ?>, 200);

                if (activityType === 4 || activityType === 5 || activityType === 6 || activityType === 7 || activityType === 8) {
                    const downsampledDataVel = downsampleData(<?php echo json_encode($velStream); ?>, 200);

                    var selectedData = {
                        hr: true,
                        cadence: false,
                        power: false,
                        elevation: false,
                        velocity: false
                    };

                    var data = {
                        hr: downsampledDataHr,
                        cadence: downsampledDataCad,
                        power: downsampledDataPower,
                        elevation: downsampledDataEle,
                        velocity: downsampledDataVel
                    };
                } else {
                    const downsampledDataPace = downsampleData(<?php echo json_encode($paceStream); ?>, 200);

                    var selectedData = {
                        hr: true,
                        cadence: false,
                        power: false,
                        elevation: false,
                        pace: false
                    };

                    var data = {
                        hr: downsampledDataHr,
                        cadence: downsampledDataCad,
                        power: downsampledDataPower,
                        elevation: downsampledDataEle,
                        pace: downsampledDataPace
                    };
                }

                var timestamps = data.hr.map(function (value, index) {
                    return index;
                });

                var dataChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: timestamps,
                        datasets: []
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        scales: {
                            x: {
                                display: false
                            },
                            y: {
                                beginAtZero: false,
                                title: {
                                    display: false
                                }
                            },
                        },
                        plugins: {
                            legend: {
                                display: true
                            },
                            tooltips: {
                                enabled: true,
                                mode: 'index',
                                intersect: false,
                            }
                        },
                    },
                });

                function downsampleData(data, threshold) {
                    if (data.length <= threshold) {
                        return data;
                    }

                    const factor = Math.ceil(data.length / threshold);
                    const downsampledData = [];

                    for (let i = 0; i < data.length; i += factor) {
                        const chunk = data.slice(i, i + factor);
                        const average = chunk.reduce((a, b) => a + b) / chunk.length;
                        downsampledData.push(average);
                    }

                    return downsampledData;
                }

                function formatPace(pace) {
                    const minutes = Math.floor(pace); // Extract whole minutes
                    let decimalFraction = pace - minutes; // Get the decimal fraction
                    let seconds = Math.round(decimalFraction * 60); // Convert the fraction to seconds
                    return `${minutes}:${seconds.toString().padStart(2, '0')} min/km`;
                }

                function updateChart() {
                    // Determine which data series to display
                    var datasets = [];

                    if (selectedData.hr) {
                        datasets.push({
                            label: 'Heart Rate',
                            data: data.hr,
                            borderColor: 'rgb(255, 0, 0)',
                            fill: false,
                        });
                    }

                    if (selectedData.cadence) {
                        datasets.push({
                            label: 'Cadence',
                            data: data.cadence,
                            borderColor: 'rgb(75, 192, 192)',
                            fill: false,
                        });
                    }

                    if (selectedData.power) {
                        datasets.push({
                            label: 'Power (W)',
                            data: data.power,
                            borderColor: 'rgb(0, 0, 255)',
                            fill: false,
                        });
                    }

                    if (selectedData.elevation) {
                        datasets.push({
                            label: 'Elevation',
                            data: data.elevation,
                            borderColor: 'rgb(0, 255, 0)',
                            fill: false,
                        });
                    }
                    if (activityType === 4 || activityType === 5 || activityType === 6 || activityType === 7 || activityType === 8) {
                        if (selectedData.velocity) {
                            datasets.push({
                                label: 'Velocity (km/h)',
                                data: data.velocity,
                                borderColor: 'rgb(255, 255, 0)',
                                fill: false,
                            });
                        }
                    } else {
                        if (activityType === 1 || activityType === 2 || activityType === 3) {
                            if (selectedData.pace) {
                                datasets.push({
                                    label: 'Pace (min/km)',
                                    data: data.pace,
                                    borderColor: 'rgb(255, 255, 0)',
                                    fill: false,
                                });
                            }
                        } else {
                            if (selectedData.pace) {
                                datasets.push({
                                    label: 'Pace (min/100m)',
                                    data: data.pace,
                                    borderColor: 'rgb(255, 255, 0)',
                                    fill: false,
                                });
                            }
                        }
                    }

                    // Update the chart
                    dataChart.data.datasets = datasets;
                    dataChart.options.scales.y.title.display = datasets.length === 1; // Show Y-axis label if only one dataset is selected
                    dataChart.update();
                }

                // Listen for checkbox changes
                document.getElementById('hrCheckbox').addEventListener('change', function () {
                    selectedData.hr = this.checked;
                    updateChart();
                });

                document.getElementById('cadenceCheckbox').addEventListener('change', function () {
                    selectedData.cadence = this.checked;
                    updateChart();
                });

                document.getElementById('powerCheckbox').addEventListener('change', function () {
                    selectedData.power = this.checked;
                    updateChart();
                });

                document.getElementById('elevationCheckbox').addEventListener('change', function () {
                    selectedData.elevation = this.checked;
                    updateChart();
                });

                if (activityType === 4 || activityType === 5 || activityType === 6 || activityType === 7 || activityType === 8) {
                    document.getElementById('velocityCheckbox').addEventListener('change', function () {
                        selectedData.velocity = this.checked;
                        updateChart();
                    });
                } else {
                    document.getElementById('paceCheckbox').addEventListener('change', function () {
                        selectedData.pace = this.checked;
                        updateChart();
                    });
                }

                // Initial chart update
                updateChart();
            </script>

            <!-- <script>
        var ctx = document.getElementById('hrChart').getContext('2d');
        
        var hrStream = <?php echo json_encode($hrStream); ?>;
        var timestamps = hrStream.map(function(value, index) {
            return index;
        });

        var hrChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: timestamps,
                datasets: [{
                    label: 'Heart Rate',
                    data: hrStream,
                    borderColor: 'rgb(75, 192, 192)',
                    fill: false,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    x: {
                        display: false, // Hide x-axis
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Heart Rate',
                        },
                    },
                },
                plugins: {
                    legend: {
                        display: false, // Hide legend
                    },
                    tooltips: {
                        enabled: true, // Enable tooltips
                        mode: 'index',
                        intersect: false,
                    }
                },
            },
        });
    </script> -->

            <div>
                <br class="d-lg-none">
                <button onclick="window.history.back();" type="button" class="w-100 btn btn-primary d-lg-none">
                    <?php echo $translationsTemplateTop['template_top_global_back']; ?>
                </button>
            </div>

        </div>

        <?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>