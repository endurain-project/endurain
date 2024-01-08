<?php
if (!isset($_SESSION)) {
    session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "gear";
$gear = [];
$editGearAction = -9000;
$deleteGearAction = -9000;

if (!isLogged()) {
    header("Location: ../login.php");
}

if (!isTokenValid($_SESSION["token"])) {
    header("Location: ../logout.php?sessionExpired=1");
}

// Load the language file based on the user's preferred language
switch ($_SESSION["preferred_language"]) {
    case 'en':
        $translationsGearGear = include $_SERVER['DOCUMENT_ROOT'] . '/lang/gear/gear/en.php';
        break;
    case 'pt':
        $translationsGearGear = include $_SERVER['DOCUMENT_ROOT'] . '/lang/gear/gear/pt.php';
        break;
    // ...
    default:
        $translationsGearGear = include $_SERVER['DOCUMENT_ROOT'] . '/lang/gear/gear/en.php';
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
    if ($deleteGearAction == 0) {
        header("Location: ../gear/gears.php?deleteGear=1");
    }
}

$gear = getGearFromId($_GET["gearID"]);
if ($gear == NULL) {
    header("Location: ../gear/gears.php?invalidGear=1");
}

$gearActivities = getGearActivities($_GET["gearID"]);

$gearTotalDistance = 0;
foreach ($gearActivities as $activity) {
    $gearTotalDistance += $activity["distance"];
}
?>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>

<div class="container mt-4">
    <h1>
        <?php echo $gear[0]["nickname"]; ?>
    </h1>
</div>

<div class="container mt-4">
    <!-- Error banners -->
    <?php if ($editGearAction == -1 || $editGearAction == -2 || $deleteGearAction == -1 || $deleteGearAction == -2) { ?>
        <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
            <i class="fa-solid fa-circle-exclamation me-1"></i>
            <div>
                <?php if ($editGearAction == -1 || $deleteGearAction == -1) { ?>
                    API ERROR |
                    <?php echo $translationsGearGear['gear_API_error_-1']; ?> (-1).
                <?php } else { ?>
                    <?php if ($editGearAction == -2 || $deleteGearAction == -2) { ?>
                        API ERROR |
                        <?php echo $translationsGearGear['gear_API_error_-2']; ?> (-2).
                    <?php } ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>

    <!-- Success banners -->
    <?php if ($editGearAction == 0) { ?>
        <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">
            <div>
                <i class="fa-regular fa-circle-check me-1"></i>
                <?php if ($editGearAction == 0) { ?>
                    <?php echo $translationsGearGear['gear_success_gearEdited']; ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>

    <div class="row row-gap-3">
        <!-- left column -->
        <div class="col-lg-3 col-md-12">
            <!-- Gear photo -->
            <div class="justify-content-center align-items-center d-flex">
                <img src=<?php if ($gear[0]["gear_type"] == 1) {
                    echo ("../img/avatar/bicycle1.png");
                } else {
                    if ($gear[0]["gear_type"] == 2) {
                        echo ("../img/avatar/running_shoe1.png");
                    } else {
                        echo ("../img/avatar/wetsuit1.png");
                    }
                } ?> alt="gearPicture" width="180" height="180">
                <!--<img src=<?php if ($gear[0]["gear_type"] == 1) {
                    echo ("../img/avatar/bicycle1.png");
                } else {
                    if ($gear[0]["gear_type"] == 2) {
                        echo ("../img/avatar/running_shoe1.png");
                    } else {
                        echo ("../img/avatar/wetsuit1.png");
                    }
                } ?> alt="gearPicture" class="rounded-circle" width="180" height="180">-->
            </div>
            <br>
            <div class="vstack justify-content-center align-items-center d-flex">
                <!-- badges  -->
                <div class="hstack justify-content-center">
                    <?php if ($gear[0]["is_active"] == 1) { ?>
                        <span
                            class="badge bg-success-subtle border border-success-subtle text-success-emphasis rounded-pill align-middle">
                            <?php echo $translationsGearGear['gear_gear_infoZone_isactive']; ?>
                        </span>
                    <?php } else { ?>
                        <span
                            class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis rounded-pill align-middle">
                            <?php echo $translationsGearGear['gear_gear_infoZone_isinactive']; ?>
                        </span>
                    <?php } ?>
                    <?php if ($gear[0]["gear_type"] == 1) { ?>
                        <span
                            class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis rounded-pill align-middle">
                            <?php echo $translationsGearGear['gear_gear_infoZone_gearisbike']; ?>
                        </span>
                    <?php } else {
                        if ($gear[0]["gear_type"] == 2) { ?>
                            <span
                                class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis rounded-pill align-middle">
                                <?php echo $translationsGearGear['gear_gear_infoZone_gearisshoe']; ?>
                            </span>
                        <?php } else { ?>
                            <span
                                class="ms-2 badge bg-primary-subtle border border-primary-subtle text-primary-emphasis rounded-pill align-middle">
                                <?php echo $translationsGearGear['gear_gear_infoZone_geariswetsuit']; ?>
                            </span>
                        <?php } ?>
                    <?php } ?>
                </div>

                <!-- edit gear zone -->
                <a class="mt-2 w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal"
                    data-bs-target="#editGearModal">
                    <?php echo $translationsGearGear['gear_gear_infoZone_editbutton']; ?>
                </a>

                <!-- Modal edit gear -->
                <div class="modal fade" id="editGearModal" tabindex="-1" aria-labelledby="editGearModal"
                    aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="editGearModal">
                                    <?php echo $translationsGearGear['gear_gear_infoZone_editbutton']; ?>
                                </h1>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"
                                    aria-label="Close"></button>
                            </div>
                            <form action="../gear/gear.php?gearID=<?php echo ($gear[0]["id"]); ?>&editGear=1"
                                method="post" enctype="multipart/form-data">
                                <div class="modal-body">
                                    <!-- brand fields -->
                                    <label for="gearBrandEdit"><b>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_brandLabel']; ?>
                                        </b></label>
                                    <input class="form-control" type="text" name="gearBrandEdit"
                                        placeholder="<?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_brandPlaceholder']; ?>"
                                        maxlength="45" value="<?php echo ($gear[0]["brand"]); ?>">
                                    <!-- model fields -->
                                    <label for="gearModelEdit"><b>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_modelLabel']; ?>
                                        </b></label>
                                    <input class="form-control" type="text" name="gearModelEdit"
                                        placeholder="<?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_modelPlaceholder']; ?>"
                                        maxlength="45" value="<?php echo ($gear[0]["model"]); ?>">
                                    <!-- nickname fields -->
                                    <label for="gearNicknameEdit"><b>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_nicknameLabel']; ?>
                                        </b></label>
                                    <input class="form-control" type="text" name="gearNicknameEdit"
                                        placeholder="<?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_nicknamePlaceholder']; ?>"
                                        maxlength="45" value="<?php echo ($gear[0]["nickname"]); ?>">
                                    <!-- gear type fields -->
                                    <label for="gearTypeEdit"><b>*
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_gearTypeLabel']; ?>
                                        </b></label>
                                    <select class="form-control" name="gearTypeEdit">
                                        <option value="1" <?php if ($gear[0]["gear_type"] == 1) { ?> selected="selected"
                                            <?php } ?>>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_gearTypeOption1']; ?>
                                        </option>
                                        <option value="2" <?php if ($gear[0]["gear_type"] == 2) { ?> selected="selected"
                                            <?php } ?>>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_gearTypeOption2']; ?>
                                        </option>
                                        <option value="3" <?php if ($gear[0]["gear_type"] == 3) { ?> selected="selected"
                                            <?php } ?>>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_gearTypeOption3']; ?>
                                        </option>
                                    </select required>
                                    <!-- date fields -->
                                    <label for="gearDateEdit"><b>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_dateLabel']; ?>
                                        </b></label>
                                    <input class="form-control" type="date" name="gearDateEdit"
                                        placeholder="<?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_datePlaceholder']; ?>"
                                        value="<?php echo date("Y-m-d", strtotime($gear[0]["created_at"])); ?>"
                                        required>
                                    <!-- gear is_active fields -->
                                    <label for="gearIsActiveEdit"><b>*
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_gearIsActiveLabel']; ?>
                                        </b></label>
                                    <select class="form-control" name="gearIsActiveEdit">
                                        <option value="1" <?php if ($gear[0]["is_active"] == 1) { ?> selected="selected"
                                            <?php } ?>>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_gearIsActiveOption1']; ?>
                                        </option>
                                        <option value="2" <?php if ($gear[0]["is_active"] == 2) { ?> selected="selected"
                                            <?php } ?>>
                                            <?php echo $translationsGearGear['gear_gear_infoZone_modal_editGear_gearIsActiveOption2']; ?>
                                        </option>
                                    </select required>
                                    *
                                    <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                </div>
                                <div class="modal-footer">
                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                        <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                    </button>
                                    <button type="submit" class="btn btn-success" name="editGear">
                                        <?php echo $translationsGearGear['gear_gear_infoZone_editbutton']; ?>
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>

                <!-- delete gear zone -->
                <a class="mt-2 w-100 btn btn-danger <?php if (count($gearActivities) != 0) {
                    echo "disabled";
                } ?>" href="#" role="button" data-bs-toggle="modal"
                    data-bs-target="#deleteGearModal" <?php if (count($gearActivities) != 0) {
                        echo 'aria-disabled="true"';
                    } ?>><?php echo $translationsGearGear['gear_gear_infoZone_deletebutton']; ?>
                </a>

                <!-- Modal delete gear -->
                <div class="modal fade" id="deleteGearModal" tabindex="-1" aria-labelledby="deleteGearModal"
                    aria-hidden="true">
                    <div class="modal-dialog">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h1 class="modal-title fs-5" id="deleteGearModal">
                                    <?php echo $translationsGearGear['gear_gear_infoZone_deletebutton']; ?>
                                </h1>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"
                                    aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <?php echo $translationsGearGear['gear_gear_infoZone_modal_deleteGear_body']; ?> <b>
                                    <?php echo ($gear[0]["nickname"]); ?>
                                </b><span>?</span>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">
                                    <?php echo $translationsTemplateTop['template_top_global_close']; ?>
                                </button>
                                <a type="button" class="btn btn-danger"
                                    href="../gear/gear.php?gearID=<?php echo ($gear[0]["id"]); ?>&deleteGear=1">
                                    <?php echo $translationsGearGear['gear_gear_infoZone_deletebutton']; ?>
                                </a>
                            </div>
                        </div>
                    </div>
                </div>
                <!-- details  -->
                <div class="vstack align-items-center">
                    <span class="mt-2"><strong>
                            <?php echo $translationsGearGear['gear_gear_infoZone_distance']; ?>:
                        </strong>
                        <?php echo number_format($gearTotalDistance / 1000, 2); ?> km
                    </span>
                    <?php if (isset($gear[0]["brand"])) { ?>
                        <span class="mt-2"><strong>
                                <?php echo $translationsGearGear['gear_gear_infoZone_brand']; ?>:
                            </strong>
                            <?php echo $gear[0]["brand"]; ?>
                        </span>
                    <?php } ?>
                    <?php if (isset($gear[0]["model"])) { ?>
                        <span class="mt-2"><strong>
                                <?php echo $translationsGearGear['gear_gear_infoZone_model']; ?>:
                            </strong>
                            <?php echo $gear[0]["model"]; ?>
                        </span>
                    <?php } ?>
                </div>
            </div>
        </div>
        <!-- right column -->
        <div class="col">
            <div>
                <!-- Gear components -->

                <!-- Last 10 gear activities -->
                <hr class="mb-2 mt-2 d-sm-none d-block">
                <div class="hstack align-items-baseline">
                    <h5>
                        <?php echo $translationsGearGear['gear_gear_gearActivities_title']; ?>
                    </h5>
                    <h7 class="ms-1">
                        <?php echo $translationsGearGear['gear_gear_gearActivities_number']; ?>
                    </h7>
                </div>
                <?php if (count($gearActivities) == 0) { ?>
                    <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
                        <i class="fa-solid fa-circle-info me-1"></i>
                        <div>
                            <?php echo $translationsGearGear['gear_gear_gearActivities_noactivities']; ?>.
                        </div>
                    </div>
                <?php } else { ?>
                    <ul class="list-group list-group-flush">
                        <?php for ($x = 0; $x < 10; $x += 1) { ?>
                            <?php if ($x < count($gearActivities)) { ?>
                                <li class="vstack list-group-item d-flex justify-content-between">
                                    <a href="../activities/activity.php?activityID=<?php echo $gearActivities[$x]["id"]; ?>">
                                        <?php echo $gearActivities[$x]["name"]; ?>
                                    </a>
                                    <span><strong>
                                            <?php echo $translationsGearGear['gear_gear_gearActivities_datelabel']; ?>:
                                        </strong>
                                        <?php echo (new DateTime($gearActivities[$x]["start_time"]))->format("d/m/y"); ?>@
                                        <?php echo (new DateTime($gearActivities[$x]["start_time"]))->format("H:i"); ?>
                                    </span>
                                </li>
                            <?php } ?>
                        <?php } ?>
                    </ul>
                <?php } ?>
            </div>
        </div>
    </div>

    <div>
        <br>
        <button onclick="window.history.back();" type="button" class="w-100 btn btn-primary d-lg-none">
            <?php echo $translationsTemplateTop['template_top_global_back']; ?>
        </button>
    </div>

</div>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>