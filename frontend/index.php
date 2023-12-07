<?php
if (!isset($_SESSION)) {
  session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "index";

if (!isLogged()) {
  header("Location: ../login.php");
}

if (!isTokenValid($_SESSION["token"])) {
  header("Location: ../logout.php?sessionExpired=1");
}

#header("Location: ../gear/gears.php");

// Load the language file based on the user's preferred language
switch ($_SESSION["preferred_language"]) {
  case 'en':
    $translationsIndex = include $_SERVER['DOCUMENT_ROOT'] . '/lang/index/en.php';
    break;
  case 'pt':
    $translationsIndex = include $_SERVER['DOCUMENT_ROOT'] . '/lang/index/pt.php';
    break;
    // ...
  default:
    $translationsIndex = include $_SERVER['DOCUMENT_ROOT'] . '/lang/index/en.php';
}

// activities
$numActivities = 0;
$activities = [];
$pageNumberActivities = 1;
$addActivityAction = -9000;
$editActivityAction = -9000;
$deleteActivityAction = -9000;

// general
$numRecords = 5;

/* Add action */
if (isset($_POST["addActivity"]) && $_GET["addActivity"] == 1) {
  $fileExtension = pathinfo($_FILES["activityGpxFileAdd"]["name"], PATHINFO_EXTENSION);
  if ($fileExtension == "gpx") {
    $addActivityAction = parseActivityGPX($_FILES["activityGpxFileAdd"]["tmp_name"]);
  }
}

if (isset($_GET["pageNumberActivities"])) {
  $pageNumberActivities = $_GET["pageNumberActivities"];
}

if (!isset($_POST["activitySearch"])) {
  $activities = getUserActivitiesPagination($pageNumberActivities, $numRecords);
  $numActivities = numUserActivities();
  $total_pages = ceil($numActivities / $numRecords);
} else {
  #$activities = getGearFromName(urlencode(trim($_POST["gearNickname"])));
  #if($activities == NULL){
  #    $numActivities=0;
  #}else{
  #    $numActivities=1;
  #}
}

$thisWeekDistances = getUserActivitiesThisWeekDistances($_SESSION["id"]);
?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<div class="container mt-4">
  <!--<h1><?php echo $translationsIndex['index_title']; ?></h1>-->
</div>

<!-- Page Container -->
<div class="container mt-4">
  <div class="row row-gap-3">
    <!-- sidebar zone -->
    <div class="col-lg-3 col-md-12">
      <div class="d-none d-lg-block mt-3 mb-3 d-flex justify-content-center">
        <div class="justify-content-center d-flex">
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
        <div class="text-center mt-3 mb-3 fw-bold">
          <a href="../settings/settings.php?profileSettings=1"><?php echo $_SESSION["name"]; ?></a>
        </div>

        <!-- this week distances zone -->
        <span class="fw-lighter"><?php echo $translationsIndex['index_userZone_thisWeekDistances_title']; ?></span>
        <div class="row">
          <div class="col">
            <span class="fw-lighter"><?php echo $translationsIndex['index_userZone_thisWeekDistances_run']; ?></span>
            <br>
            <?php if ($thisWeekDistances["run"] != null) { ?>
              <?php echo number_format(($thisWeekDistances["run"] / 1000), 2); ?> km
            <?php } else { ?>
              0 km
            <?php } ?>
          </div>
          <div class="col border-start border-opacity-50">
            <span class="fw-lighter"><?php echo $translationsIndex['index_userZone_thisWeekDistances_bike']; ?></span>
            <br>
            <?php if ($thisWeekDistances["bike"] != null) { ?>
              <?php echo number_format(($thisWeekDistances["bike"] / 1000), 2); ?> km
            <?php } else { ?>
              0 km
            <?php } ?>
          </div>
          <div class="col border-start border-opacity-50">
            <span class="fw-lighter"><?php echo $translationsIndex['index_userZone_thisWeekDistances_swim']; ?></span>
            <br>
            <?php if ($thisWeekDistances["swim"] != null) { ?>
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
      </div>

      <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addActivityModal"><?php echo $translationsIndex['index_sidebar_addActivity']; ?></a>

      <!-- Modal add actvity -->
      <div class="modal fade" id="addActivityModal" tabindex="-1" aria-labelledby="addActivityModal" aria-hidden="true">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h1 class="modal-title fs-5" id="addActivityModal"><?php echo $translationsIndex['index_sidebar_addActivity']; ?></h1>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <form action="../index.php?addActivity=1" method="post" enctype="multipart/form-data">
              <div class="modal-body">

                <!-- date fields -->
                <label for="activityGpxFileAdd"><b>* <?php echo $translationsIndex['index_sidebar_addActivity_modal_addGpxFile_placeholder']; ?></b></label>
                <input class="form-control" type="file" name="activityGpxFileAdd" accept=".gpx" required>
                <p>* <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?></p>
              </div>
              <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                <button type="submit" class="btn btn-success" name="addActivity"><?php echo $translationsIndex['index_sidebar_addActivity']; ?></button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div class="col">
      <!-- Error banners -->
      <?php if ($activities == -1 || $activities == -2 || $addActivityAction == -1 || $addActivityAction == -2 || $addActivityAction == -3 || $addActivityAction == -4 || (isset($_GET["invalidActivity"]) && $_GET["invalidActivity"] == 1)) { ?>
        <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
          <i class="fa-solid fa-circle-exclamation me-1"></i>
          <div>
            <?php if ($activities == -1 || $addActivityAction == -1) { ?>
              API ERROR | <?php echo $translationsIndex['index_sidebar_addActivity_API_error_-1']; ?> (-1).
            <?php } else { ?>
              <?php if ($activities == -2 || $addActivityAction == -2) { ?>
                API ERROR | <?php echo $translationsIndex['index_sidebar_addActivity_API_error_-2']; ?> (-2).
              <?php } else { ?>
                <?php if ($addActivityAction == -3) { ?>
                  <?php echo $translationsIndex['index_sidebar_addActivity_fileExtensionNotSupported_-3']; ?> (-3).
                <?php } else { ?>
                  <?php if ($addActivityAction == -4) { ?>
                    <?php echo $translationsIndex['index_sidebar_addActivity_GPXError_-4']; ?> (-4).
                  <?php } else { ?>
                    <?php if ($_GET["invalidActivity"] == 1) { ?>
                      <?php echo $translationsIndex['index_sidebar_invalidActivity']; ?>.
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
      <?php if ($activities == NULL) { ?>
        <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
          <i class="fa-solid fa-triangle-exclamation me-1"></i>
          <div>
            <?php if ($activities == NULL) { ?>
              <?php echo $translationsIndex['index_sidebar_addActivity_info_searchActivity_NULL']; ?> (NULL).
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
          </div>
        </div>
      <?php } ?>

      <!-- Success banners -->
      <?php if ($addActivityAction == 0 || (isset($_GET["deleteActivity"]) && $_GET["deleteActivity"] == 1)) { ?>
        <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
          <div>
            <i class="fa-regular fa-circle-check me-1"></i>
            <?php if ($addActivityAction == 0) { ?>
              <?php echo $translationsIndex['index_sidebar_addActivity_success_activityAdded']; ?>
            <?php } else { ?>
              <?php if (isset($_GET["deleteActivity"]) && $_GET["deleteActivity"] == 1) { ?>
                <?php echo $translationsIndex['index_sidebar_addActivity_success_activityDeleted']; ?>
              <?php } ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
          </div>
        </div>
      <?php } ?>

      <!--<div class="btn-group mb-3 d-flex" role="group"  aria-label="Activities radio toggle button group">
        <input type="radio" class="btn-check" name="btnradio" id="btnRadioUserActivities" autocomplete="off" checked>
        <label class="btn btn-outline-primary w-100" for="btnRadioUserActivities"><?php echo $translationsIndex['activity_radio_userActivities']; ?></label>

        <input type="radio" class="btn-check" name="btnradio" id="btnRadioFollowersActivities" autocomplete="off">
        <label class="btn btn-outline-primary w-100" for="btnRadioFollowersActivities"><?php echo $translationsIndex['activity_radio_followersActivities']; ?></label>
      </div>-->

      <div id="userActivitiesDiv" style="display: block;">
        <!-- user activities list -->
        <?php foreach ($activities as $activity) { ?>
          <div class="card">
            <div class="card-body">
              <div class="d-flex align-items-center">
                <img src=<?php if (is_null($_SESSION["photo_path"])) {
                            if ($_SESSION["gender"] == 1) {
                              echo ("../img/avatar/male1.png");
                            } else {
                              echo ("../img/avatar/female1.png");
                            }
                          } else {
                            echo ($_SESSION["photo_path"]);
                          } ?> alt="userPicture" class="rounded-circle" width="55" height="55">
                <div class="ms-3 me-3">
                  <div class="fw-bold">
                    <a href="activities/activity.php?activityID=<?php echo ($activity["id"]); ?>" class="link-underline-opacity-25 link-underline-opacity-100-hover"><?php echo ($activity["name"]); ?></a>
                  </div>
                  <h7><?php if ($activity["activity_type"] == 1) {
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
                      } ?> <?php echo (new DateTime($activity["start_time"]))->format("d/m/y"); ?>@<?php echo (new DateTime($activity["start_time"]))->format("H:i"); ?><?php if (isset($activity["city"]) || isset($activity["country"])) {
                                                                                                                                                                        echo " - ";
                                                                                                                                                                      } ?><?php if (isset($activity["city"]) && !empty($activity["city"])) {
                                                                                                                                                                                                                                                          echo $activity["city"] . ", ";
                                                                                                                                                                                                                                                        } ?><?php if (isset($activity["country"]) && !empty($activity["country"])) {
                                                                                                                                                                                                                                                                                                                                                            echo $activity["country"];
                                                                                                                                                                                                                                                                                                                                                          } ?></h7>
                </div>
              </div>
              <div class="row d-flex mt-3">
                <div class="col">
                  <span class="fw-lighter"><?php echo $translationsIndex['index_activities_detail_distance']; ?></span>
                  <br>
                  <?php if ($activity["activity_type"] != 9) { ?>
                    <?php echo number_format(($activity["distance"] / 1000), 2); ?> km
                  <?php } else { ?>
                    <?php echo ($activity["distance"]); ?> m
                  <?php } ?>
                </div>
                <div class="col border-start border-opacity-50">
                  <span class="fw-lighter"><?php echo $translationsIndex['index_activities_detail_time']; ?></span>
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
                    <span class="fw-lighter"><?php echo $translationsIndex['index_activities_detail_elevation_gain']; ?></span>
                    <br>
                    <?php echo ($activity["elevation_gain"]); ?> m
                  <?php } else { ?>
                    <?php if ($activity["activity_type"] == 1 || $activity["activity_type"] == 2 || $activity["activity_type"] == 3) { ?>
                      <span class="fw-lighter"><?php echo $translationsIndex['index_activities_detail_pace']; ?></span>
                      <br>
                      <?php echo floor(($activity["pace"] * 1000) / 60) . ":" . number_format((((($activity["pace"] * 1000) / 60) - floor(($activity["pace"] * 1000) / 60)) * 60), 0); ?> min/km
                    <?php } else { ?>
                      <?php if ($activity["activity_type"] == 9) { ?>
                        <span class="fw-lighter"><?php echo $translationsIndex['index_activities_detail_pace']; ?></span>
                        <br>
                        <?php echo floor(($activity["pace"] * 100) / 60) . ":" . number_format((((($activity["pace"] * 100) / 60) - floor(($activity["pace"] * 100) / 60)) * 60), 0); ?> min/km
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
                <span class="fw-lighter ms-3 me-3"><?php echo $translationsIndex['index_activities_stravaText1']; ?><a href="https://www.strava.com/activities/<?php echo $activity['strava_activity_id']; ?>" target="_blank" rel="noopener noreferrer"><?php echo $translationsIndex['index_activities_stravaText2']; ?></a></span>
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

            var latlngs = waypoints.map(function(waypoint) {
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

        <?php if (!isset($_POST["activitySearch"])) { ?>
          <br>
          <nav>
            <ul class="pagination justify-content-center">
              <li class="page-item <?php if ($pageNumberActivities == 1) {
                                      echo "disabled";
                                    } ?>"><a class="page-link" href="?pageNumberActivities=1">«</a></li>
              <?php for ($i = 1; $i <= $total_pages; $i++) { ?>
                <li class="page-item <?php if ($i == $pageNumberActivities) {
                                        echo "active";
                                      } ?>"><a class="page-link" href="?pageNumberActivities=<?php echo ($i); ?>"><?php echo ($i); ?></a></li>
              <?php } ?>
              <li class="page-item <?php if ($pageNumberActivities == $total_pages) {
                                      echo "disabled";
                                    } ?>"><a class="page-link" href="?pageNumberActivities=<?php echo ($total_pages); ?>">»</a></li>
            </ul>
          </nav>
        <?php } ?>
      </div>

      <div class="card" id="followersActivitiesDiv" style="display: none;">

      </div>

      <script>
        // Get references to the radio buttons and the div elements
        const userActivitiesRadio = document.getElementById('btnRadioUserActivities');
        const followersActivitiesRadio = document.getElementById('btnRadioFollowersActivities');
        const userActivitiesDiv = document.getElementById('userActivitiesDiv');
        const followersActivitiesDiv = document.getElementById('followersActivitiesDiv');

        // Add a change event listener to the radio buttons
        userActivitiesRadio.addEventListener('change', () => {
          userActivitiesDiv.style.display = 'block';
          followersActivitiesDiv.style.display = 'none';
        });

        followersActivitiesRadio.addEventListener('change', () => {
          userActivitiesDiv.style.display = 'none';
          followersActivitiesDiv.style.display = 'block';
        });
      </script>

    </div>
  </div>
  <!-- End Page Container -->
</div>



<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>