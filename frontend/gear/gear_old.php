<?php
    if(!isset($_SESSION)){
		session_start();
	}
		
    require_once $_SERVER['DOCUMENT_ROOT']."/inc/sqlFunctions.php"; 
    
    $page="gear";
    $addGearAction = -9000;
    $editGearAction = -9000;
    $deleteGearAction = -9000;
    $numGear = 0;
    $gears = [];
    $pageNumber = 1;
    $numRecords = 5;

    if(!isLogged()){
        header("Location: ../login.php");
    }

    if(!isTokenValid($_SESSION["token"])){
        header("Location: ../logout.php?sessionExpired=1");
    }

    // Load the language file based on the user's preferred language
    switch ($_SESSION["preferred_language"]) {
        case 'en':
            $translationsGearGear = include $_SERVER['DOCUMENT_ROOT'].'/lang/gear/en.php';
            break;
        case 'pt':
            $translationsGearGear = include $_SERVER['DOCUMENT_ROOT'].'/lang/gear/pt.php';
            break;
        // ...
        default:
            $translationsGearGear = include $_SERVER['DOCUMENT_ROOT'].'/lang/gear/en.php';

    }

    /* Add action */
    if(isset($_POST["addGear"]) && $_GET["addGear"] == 1){
        if(empty(trim($_POST["gearBrandAdd"]))){
            $_POST["gearBrandAdd"] = NULL;
        }
        if(empty(trim($_POST["gearModelAdd"]))){
            $_POST["gearModelAdd"] = NULL;
        }
        
        $addGearAction = newGear(urlencode(trim($_POST["gearBrandAdd"])), urlencode(trim($_POST["gearModelAdd"])), urlencode(trim($_POST["gearNicknameAdd"])), $_POST["gearTypeAdd"], $_SESSION["id"], $_POST["gearDateAdd"]);
    }

    /* Edit action */
    if (isset($_POST["editGear"]) && $_GET["editGear"] == 1) {
        if(empty(trim($_POST["gearBrandEdit"]))){
            $_POST["gearBrandEdit"] = NULL;
        }
        if(empty(trim($_POST["gearModelEdit"]))){
            $_POST["gearModelEdit"] = NULL;
        }
        $editGearAction = editGear($_GET["gearID"], urlencode(trim($_POST["gearBrandEdit"])), urlencode(trim($_POST["gearModelEdit"])), urlencode(trim($_POST["gearNicknameEdit"])), $_POST["gearTypeEdit"], $_POST["gearDateEdit"], $_POST["gearIsActiveEdit"]);
    }

    /* Delete gear */
    if(isset($_GET["deleteGear"]) && $_GET["deleteGear"] == 1){
        $deleteGearAction = deleteGear($_GET["gearID"]);
    }

    if(isset($_GET["pageNumber"])){
        $pageNumber = $_GET["pageNumber"];
    }

    if(!isset($_POST["gearSearch"])){
        $gears = getGearPagination($pageNumber, $numRecords);
        $numGear = numGear();
        $total_pages = ceil($numGear / $numRecords);
    }else{
        $gears = getGearFromNickname(urlencode(trim($_POST["gearNickname"])));
        if($gears == NULL){
            $numGear=0;
        }else{
            $numGear=1;
        }
    }
?>

<?php require_once $_SERVER['DOCUMENT_ROOT']."/inc/Template-Top.php" ?>

<div class="container mt-4">
    <h1><?php echo $translationsGearGear['gear_title']; ?></h1>
</div>

<div class="container mt-4">
    <!-- Error banners -->
    <?php if($gears == -1 || $gears == -2 || $editGearAction == -1 || $editGearAction == -2 || $editGearAction == -3 || $deleteGearAction == -1 || $deleteGearAction == -2 || $deleteGearAction == -3 || $addGearAction == -1 || $addGearAction == -2 || $addGearAction == -3){ ?>
        <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
            <i class="fa-solid fa-circle-exclamation me-1"></i>
            <div>
                <?php if($gears == -1 || $addGearAction == -1 || $editGearAction == -1 || $deleteGearAction == -1){ ?>
                    API ERROR | <?php echo $translationsGearGear['gear_gear_API_error_-1']; ?> (-1).
                <?php }else{ ?>
                    <?php if($gears == -2 || $addGearAction == -2 || $editGearAction == -2 || $deleteGearAction == -2){ ?>
                        API ERROR | <?php echo $translationsGearGear['gear_gear_API_error_-2']; ?> (-2).
                    <?php }else{ ?>
                        <?php if($editGearAction == -3){ ?>
                            <?php echo $translationsGearGear['gear_gear_error_editGear_-3']; ?> (-3).
                        <?php }else{ ?>
                            <?php if($addGearAction == -3){ ?>
                                <?php echo $translationsGearGear['gear_gear_error_addGear_-3']; ?> (-3).
                            <?php } ?>
                        <?php } ?>
                    <?php } ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>

    <!-- Info banners -->
    <?php if($gears == NULL){ ?>
        <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
            <i class="fa-solid fa-triangle-exclamation me-1"></i>
            <div>
                <?php if($users == NULL){ ?>
                    <?php echo $translationsGearGear['gear_gear_error_searchGear_NULL']; ?> (NULL).
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>

    <!-- Success banners -->
    <?php if($addGearAction == 0 || $editGearAction == 0 || $deleteGearAction == 0){ ?>
        <div class="alert alert-success alert-dismissible d-flex align-items-center" role="alert">   
            <div>
                <i class="fa-regular fa-circle-check me-1"></i> 
                <?php if($addGearAction == 0){ ?>
                    <?php echo $translationsGearGear['gear_gear_success_gearAdded']; ?>
                <?php }else{ ?>
                    <?php if($editGearAction == 0){ ?>
                        <?php echo $translationsGearGear['gear_gear_success_gearEdited']; ?>
                    <?php }else{ ?>
                        <?php if($deleteGearAction == 0){ ?>
                            <?php echo $translationsGearGear['gear_gear_success_gearDeleted']; ?>
                        <?php } ?>
                    <?php } ?>
                <?php } ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>
        </div>
    <?php } ?>
    
    <div class="row row-gap-3">
        <div class="col-lg-4 col-md-12">
            <!-- Add gear zone -->
            <p><?php echo $translationsGearGear['gear_gear_buttonLabel_addGear']; ?></p>
            <a class="w-100 btn btn-primary" href="#" role="button" data-bs-toggle="modal" data-bs-target="#addGearModal"><?php echo $translationsGearGear['gear_gear_button_addGear']; ?></a>
            
            <!-- Modal add gear -->
            <div class="modal fade" id="addGearModal" tabindex="-1" aria-labelledby="addGearModal" aria-hidden="true">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h1 class="modal-title fs-5" id="addGearModal"><?php echo $translationsGearGear['gear_gear_modal_addGear_title']; ?></h1>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                            <form action="../gear/gear.php?addGear=1" method="post" enctype="multipart/form-data">
                            <div class="modal-body">
                                <!-- brand fields -->  
                                <label for="gearBrandAdd"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_brandLabel']; ?></b></label>
                                <input class="form-control" type="text" name="gearBrandAdd" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_brandPlaceholder']; ?>" maxlength="45" value="<?php echo($_POST["gearBrandAdd"]); ?>">
                                <!-- model fields -->
                                <label for="gearModelAdd"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_modelLabel']; ?></b></label>
                                <input class="form-control" type="text" name="gearModelAdd" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_modelPlaceholder']; ?>" maxlength="45" value="<?php echo($_POST["gearModelAdd"]); ?>">
                                <!-- nickname fields -->
                                <label for="gearNicknameAdd"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_nicknameLabel']; ?></b></label>
                                <input class="form-control" type="text" name="gearNicknameAdd" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_nicknamePlaceholder']; ?>" maxlength="45" value="<?php echo($_POST["gearNicknameAdd"]); ?>">
                                <!-- gear type fields -->
                                <label for="gearTypeAdd"><b>* <?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeLabel']; ?></b></label>
                                <select class="form-control" name="gearTypeAdd">
                                    <option value="1" <?php if($_POST["gearTypeAdd"] == 1){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption1']; ?></option>
                                    <option value="2" <?php if($_POST["gearTypeAdd"] == 2){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption2']; ?></option>
                                    <option value="3" <?php if($_POST["gearTypeAdd"] == 3){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption3']; ?></option>
                                </select required>
                                <!-- date fields -->
                                <label for="gearDateAdd"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_dateLabel']; ?></b></label>
                                <input class="form-control" type="date" name="gearDateAdd" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_datePlaceholder']; ?>" value="<?php echo($_POST["gearDateAdd"]); ?>" required>
                                * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                <button type="submit" class="btn btn-success" name="addGear"><?php echo $translationsGearGear['gear_gear_modal_addGear_title']; ?></button>
                            </div>
                        </form>
                    </div>
                </div>
            </div>

            <br>
            <p><?php echo $translationsGearGear['gear_gear_buttonLabel_searchGear']; ?></p>
            <form action="../gear/gear.php" method="post">
                <div class="mb-3">
                    <!--<label for="userUsername"><b>Username</b></label>-->
                    <input class="form-control" type="text" name="gearNickname" placeholder="<?php echo $translationsGearGear['gear_gear_form_searchGear_nicknamePlaceholder']; ?>" required>
                </div>
                <button class="w-100 btn btn-success" type="submit" name="gearSearch"><?php echo $translationsGearGear['gear_gear_button_searchGear']; ?></button>
            </form>
            <?php if(isset($_POST["gearSearch"])){ ?>
                <br>
                <a class="w-100 btn btn-primary" href="../gear/gear.php" role="button"><?php echo $translationsTemplateTop['template_top_global_button_listAll']; ?></a>
            <?php } ?>
        </div>
        <div class="col">
            <?php if($gears == -1 || $numGear == -1 || $gears == -2){ ?>
                <div class="alert alert-danger alert-dismissible d-flex align-items-center" role="alert">
                    <i class="fa-solid fa-circle-exclamation"></i>
                    <div>
                        <?php if($gears == -1 || $numGear == -1 || $gears == -2){ ?>
                            <?php echo $translationsGearGear['gear_gear_error_listGear_-1-2']; ?> (-1/-2).
                        <?php } ?>
                    </div>
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            <?php }else{ ?>
                <!-- Info banners -->
                <?php if($gears == -3){ ?>
                    <div class="alert alert-warning alert-dismissible d-flex align-items-center" role="alert">
                        <i class="fa-solid fa-triangle-exclamation"></i>
                        <div>
                            <?php if($gears == -3){ ?>
                                <?php echo $translationsGearGear['gear_gear_error_listGear_-3']; ?> (-3).
                            <?php } ?>
                        </div>
                        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                    </div>
                <?php }else{ ?>
                    <p><?php echo $translationsGearGear['gear_gear_list_title1']; ?> <?php echo ($numGear); ?> <?php echo $translationsGearGear['gear_gear_list_title2']; ?> (<?php echo $numRecords; ?> <?php echo $translationsGearGear['gear_gear_list_title3']; ?>:</p>
                    <ul class="list-group list-group-flush">
                        <?php foreach ($gears as $gear) { ?>
                            <li class="list-group-item d-flex justify-content-between">
                                <div class="d-flex align-items-center">
                                    <img src=<?php if($gear["gear_type"] == 1){ echo ("../img/avatar/male1.png"); }else{ if($gear["gear_type"] == 2){ echo ("../img/avatar/male1.png"); }else{ echo ("../img/avatar/female1.png"); }} ?> alt="gearPicture" class="rounded-circle" width="55" height="55">
                                    <div class="ms-3">
                                        <div class="fw-bold">
                                            <?php echo ($gear["nickname"]); ?>
                                        </div>
                                        <b><?php echo $translationsGearGear['gear_gear_gear_type']; ?></b><?php if($gear["gear_type"] == 1){ echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption1']; }else{ if($gear["gear_type"] == 2){ echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption2']; }else{ if($gear["gear_type"] == 3){ echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption3']; }}} ?>
                                        </br>
                                        <?php if($gear["is_active"] == 1){ ?>
                                            <span class="badge bg-success-subtle border border-success-subtle text-success-emphasis align-middle"><?php echo $translationsGearGear['gear_gear_list_isactive']; ?></span>
                                        <?php }else{ ?>
                                            <span class="badge bg-danger-subtle border border-danger-subtle text-danger-emphasis align-middle"><?php echo $translationsGearGear['gear_gear_list_isinactive']; ?></span>
                                        <?php } ?>
                                    </div>
                                </div>
                                <div>
                                    <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#editGearModal<?php echo ($gear["id"]); ?>"><i class="fa-solid fa-pen-to-square"></i></a>

                                    <!-- Modal edit user -->
                                    <div class="modal fade" id="editGearModal<?php echo ($gear["id"]); ?>" tabindex="-1" aria-labelledby="editGearModal<?php echo ($gear["id"]); ?>" aria-hidden="true">
                                        <div class="modal-dialog">
                                            <div class="modal-content">
                                                <div class="modal-header">
                                                    <h1 class="modal-title fs-5" id="editGearModal<?php echo ($user["id"]); ?>"><?php echo $translationsGearGear['gear_gear_modal_editGear_title']; ?></h1>
                                                    <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                                </div>
                                                <form action="../gear/gear.php?gearID=<?php echo ($gear["id"]); ?>&editGear=1" method="post" enctype="multipart/form-data">
                                                    <div class="modal-body">
                                                        <!-- brand fields -->  
                                                        <label for="gearBrandEdit"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_brandLabel']; ?></b></label>
                                                        <input class="form-control" type="text" name="gearBrandEdit" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_brandPlaceholder']; ?>" maxlength="45" value="<?php echo($gear["brand"]); ?>">
                                                        <!-- model fields -->
                                                        <label for="gearModelEdit"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_modelLabel']; ?></b></label>
                                                        <input class="form-control" type="text" name="gearModelEdit" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_modelPlaceholder']; ?>" maxlength="45" value="<?php echo($gear["model"]); ?>">
                                                        <!-- nickname fields -->
                                                        <label for="gearNicknameEdit"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_nicknameLabel']; ?></b></label>
                                                        <input class="form-control" type="text" name="gearNicknameEdit" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_nicknamePlaceholder']; ?>" maxlength="45" value="<?php echo($gear["nickname"]); ?>">
                                                        <!-- gear type fields -->
                                                        <label for="gearTypeEdit"><b>* <?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeLabel']; ?></b></label>
                                                        <select class="form-control" name="gearTypeEdit">
                                                            <option value="1" <?php if($gear["gear_type"] == 1){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption1']; ?></option>
                                                            <option value="2" <?php if($gear["gear_type"] == 2){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption2']; ?></option>
                                                            <option value="3" <?php if($gear["gear_type"] == 3){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_addEditUser_gearTypeOption3']; ?></option>
                                                        </select required>
                                                        <!-- date fields -->
                                                        <label for="gearDateEdit"><b><?php echo $translationsGearGear['gear_gear_modal_addEditGear_dateLabel']; ?></b></label>
                                                        <input class="form-control" type="date" name="gearDateEdit" placeholder="<?php echo $translationsGearGear['gear_gear_modal_addEditGear_datePlaceholder']; ?>" value="<?php echo (new DateTime($gear["created_at"]))->format('Y-m-d'); ?>" required>
                                                        <!-- is active fields -->
                                                        <label for="gearIsActiveEdit"><b>* <?php echo $translationsGearGear['gear_gear_modal_editUser_gearIsActiveLabel']; ?></b></label>
                                                        <select class="form-control" name="gearIsActiveEdit">
                                                            <option value="1" <?php if($gear["is_active"] == 1){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_editUser_gearIsActiveOption1']; ?></option>
                                                            <option value="0" <?php if($gear["is_active"] == 0){ ?> selected="selected" <?php } ?>><?php echo $translationsGearGear['gear_gear_modal_editUser_gearIsActiveOption2']; ?></option>
                                                        </select required>
                                                        * <?php echo $translationsTemplateTop['template_top_global_requiredFields']; ?>
                                                    </div>
                                                    <div class="modal-footer">
                                                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                                        <button type="submit" class="btn btn-success" name="editGear"><?php echo $translationsGearGear['gear_gear_modal_editGear_title']; ?></button>
                                                    </div>
                                                </form>
                                            </div>
                                        </div>
                                    </div>
                                    <a class="btn btn-link btn-lg" href="#" role="button" data-bs-toggle="modal" data-bs-target="#deleteGearModal<?php echo ($gear["id"]); ?>"><i class="fa-solid fa-trash-can"></i></a>

                                    <!-- Modal -->
                                    <div class="modal fade" id="deleteGearModal<?php echo ($gear["id"]); ?>" tabindex="-1" aria-labelledby="deleteGearModal<?php echo ($gear["id"]); ?>" aria-hidden="true">
                                        <div class="modal-dialog">
                                            <div class="modal-content">
                                                <div class="modal-header">
                                                    <h1 class="modal-title fs-5" id="deleteGearModal<?php echo ($gear["id"]); ?>"><?php echo $translationsGearGear['gear_gear_modal_deleteGear_title']; ?></h1>
                                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                                                </div>
                                                <div class="modal-body">
                                                <?php echo $translationsGearGear['gear_gear_modal_deleteGear_body']; ?> <b><?php echo ($gear["nickname"]); ?></b>?
                                                </div>
                                                <div class="modal-footer">
                                                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal"><?php echo $translationsTemplateTop['template_top_global_close']; ?></button>
                                                    <a type="button" class="btn btn-danger" href="../gear/gear.php?gearID=<?php echo ($gear["id"]); ?>&deleteGear=1"><?php echo $translationsGearGear['gear_gear_modal_deleteGear_title']; ?></a>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </li>
                        <?php } ?>
                    </ul>
                    <?php if(!isset($_POST["gearSearch"])){ ?>
                        <br>
                        <nav>
                            <ul class="pagination justify-content-center">
                                <li class="page-item <?php if($pageNumber == 1){ echo "disabled"; } ?>"><a class="page-link" href="?pageNumber=1">«</a></li>
                                <?php for ($i = 1; $i <= $total_pages; $i++) { ?>
                                    <li class="page-item <?php if($i == $pageNumber){ echo "active"; } ?>"><a class="page-link" href="?pageNumber=<?php echo ($i);?>"><?php echo ($i);?></a></li>
                                <?php } ?>
                                <li class="page-item <?php if($pageNumber == $total_pages){ echo "disabled"; } ?>"><a class="page-link" href="?pageNumber=<?php echo ($total_pages);?>">»</a></li>
                            </ul>
                        </nav>
                    <?php } ?>
                <?php } ?>
            <?php } ?>
        </div>
    </div>
    <div>
        <br>
        <button onclick="window.history.back();" type="button" class="w-100 btn btn-primary d-lg-none"><?php echo $translationsTemplateTop['template_top_global_back']; ?></button>
    </div>

</div>

<?php require_once $_SERVER['DOCUMENT_ROOT']."/inc/Template-Bottom.php" ?>