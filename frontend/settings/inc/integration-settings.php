<?php
    // Load the language file based on the user's preferred language
    switch ($_SESSION["preferred_language"]) {
        case 'en':
            $translationsSettingsIntegrationSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/integration-settings/en.php';
            break;
        case 'pt':
            $translationsSettingsIntegrationSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/integration-settings/pt.php';
            break;
        // ...
        default:
            $translationsSettingsIntegrationSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/inc/integration-settings/en.php';
    }

    $strava_gear_result = -9000;
    $strava_activities_result = -9000;

    if (isset($_GET["linkStrava"]) && $_GET["linkStrava"] == 1) {
        $state = bin2hex(random_bytes(16));
        $generate_user_state = setUniqueUserStateStravaLink($state);
        if ($generate_user_state == 0) {
            linkStrava($state);
        }
    }

    if (isset($_GET["stravaLinked"]) && $_GET["stravaLinked"] == 1) {
        setUserRelatedInfoSession($_SESSION["token"]);
        $unset_user_state = unsetUniqueUserStateStravaLink();
    }

    if(isset($_GET["getUserStravaActivities"]) && $_GET["getUserStravaActivities"] == 1){
        $strava_activities_result = getStravaActivitiesLastDays(7);
    }

    if(isset($_GET["getUserStravaGear"]) && $_GET["getUserStravaGear"] == 1){
        $strava_gear_result = getStravaGear();
    }
?>

<!-- Error banners -->
<?php if ($strava_gear_result == -1 || $strava_gear_result == -2 || $strava_activities_result == -1 || $strava_activities_result == -2) { ?>
    <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
        <i class="fa-solid fa-circle-exclamation me-1"></i>
        <div>
            <?php if ($strava_gear_result == -1 || $strava_activities_result == -1) { ?>
                API ERROR | <?php echo $translationsSettings['settings_API_error_-1']; ?> (-1).
            <?php } else { ?>
                <?php if ($strava_gear_result == -2 || $strava_activities_result == -2) { ?>
                    API ERROR | <?php echo $translationsSettings['settings_API_error_-2']; ?> (-2).
                <?php } ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    </div>
<?php } ?>

<!-- Info banners -->

<!-- Success banners -->
<?php if ((isset($_GET["stravaLinked"]) && $_GET["stravaLinked"] == 1) || $strava_gear_result == 0 || $strava_activities_result == 0) { ?>
    <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
        <div>
            <i class="fa-regular fa-circle-check me-1"></i>
            <?php if (isset($_GET["stravaLinked"]) && $_GET["stravaLinked"] == 1) { ?>
                <?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_success_stravaLinked']; ?>
            <?php }else{ ?>
                <?php if ($strava_gear_result == 0) { ?>
                    <?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_success_stravaGear']; ?>
                <?php }else{ ?>
                    <?php if ($strava_activities_result == 0) { ?>
                        <?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_success_stravaActivities']; ?>
                    <?php } ?>
                <?php } ?>
            <?php } ?>
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    </div>
<?php } ?>

<div class="row row-gap-3 row-cols-sm-3 align-items-center">
    <div class="col">
        <div class="card text-center">
            <img src="../img/strava/api_logo_cptblWith_strava_stack_light.svg" alt="Compatible with Strava image" class="card-img-top">
            <div class="card-body">
                <h4 class="card-title"><?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_strava_title']; ?></h4>
                <p class="card-text"><?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_strava_body']; ?></p>
                    <a href="../settings/settings.php?integrationSettings=1&linkStrava=1" class="btn btn-primary <?php if ($_SESSION["is_strava_linked"] == 1) { echo "disabled"; } ?>"><?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_connect_button']; ?></a>
                <?php if ($_SESSION["is_strava_linked"] == 1) { ?>
                    <hr>
                    <a href="../settings/settings.php?integrationSettings=1&getUserStravaActivities=1" class="btn btn-primary"><?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_retrieve_last_week_activities_button']; ?></a>
                    
                    <a href="../settings/settings.php?integrationSettings=1&getUserStravaGear=1" class="btn btn-primary mt-3"><?php echo $translationsSettingsIntegrationSettings['settings_integration_settings_retrieve_gear_button']; ?></a>
                <?php } ?>
            </div>
        </div>
    </div>
</div>