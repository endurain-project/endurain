<?php
    // Check if the "preferred_language" key is set in the session
    if (isset($_SESSION["preferred_language"])) {
        // Load the language file based on the user's preferred language
        switch ($_SESSION["preferred_language"]) {
            case 'en':
                $translationsTemplateTop = include $_SERVER['DOCUMENT_ROOT'].'/lang/inc/Template-Top/en.php';
                break;
            case 'pt':
                $translationsTemplateTop = include $_SERVER['DOCUMENT_ROOT'].'/lang/inc/Template-Top/pt.php';
                break;
            // ...
            default:
                $translationsTemplateTop = include $_SERVER['DOCUMENT_ROOT'].'/lang/inc/Template-Top/en.php';
        }
    } else {
        // Set a default language or handle the case when "preferred_language" is not set
        $translationsTemplateTop = include $_SERVER['DOCUMENT_ROOT'].'/lang/inc/Template-Top/en.php';
    }
?>

<!DOCTYPE html>
<html data-bs-theme="default" lang="pt">
    <head>
		<meta charset="UTF-8">
		<meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Gear Guardian</title>
        <!--<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-GLhlTQ8iRABdZLl6O3oVMWSktQOp6b7In1Zl3/Jr59b6EGGoI1aFkw7cmDA6j6gD" crossorigin="anonymous">
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js" integrity="sha384-w76AqPfDkMBDXo30jS1Sgez6pr3x5MlQ1ZAGC+nuZB+EYdgRZgiwxhTBTkF7CXvN" crossorigin="anonymous"></script>-->
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-T3c6CoIi6uLrA9TneNEoa7RxnatzjcDSCmG1MXxSR1GAsXEV/Dwwykc2MPK8M2HN" crossorigin="anonymous">
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js" integrity="sha384-C6RzsynM9kWDrMNeT87bh95OGNyZPhcTNXj1NW7RuBCsyN/o0jlpcV8Qyq46cDfL" crossorigin="anonymous"></script>
        <!--<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.2.0/chart.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/2.9.4/Chart.js"></script>-->
        <script src="https://kit.fontawesome.com/8c44ee63d9.js"></script>
		<link rel="shortcut icon" href="../img/logo/logo.png">
		<link rel="apple-touch-icon" href="../img/logo/logo.png">
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.7.1/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.7.1/dist/leaflet.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
	</head>
	<body>
        <script>
            // Used to toggle the menu on small screens when clicking on the menu button
            function showNav() {
                var x = document.getElementById("navSmallScreens");
                if (x.className.indexOf("w3-show") == -1) {
                    x.className += " w3-show";
                } else {
                    x.className = x.className.replace(" w3-show", "");
                }
            }

            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            const html = document.querySelector('html');
            if (prefersDark) {
                html.setAttribute('data-bs-theme', 'dark');
            } else {
                html.setAttribute('data-bs-theme', 'default');
            }
        </script>
        <nav class="navbar navbar-expand-lg bg-body-tertiary">
            <div class="container-fluid">
                <!--<img src="../img/logo/logo.png" alt="Logo" width="24" height="24" class="rounded-circle d-inline-block align-text-top m-2">-->
                <img src="../img/logo/logo.png" alt="Logo" width="30" class="d-inline-block align-text-top m-2">
                <a class="navbar-brand" href="../index.php">Gear Guardian</a>
                <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNavAltMarkup" aria-controls="navbarNavAltMarkup" aria-expanded="false" aria-label="Toggle navigation">
                    <span class="navbar-toggler-icon"></span>
                </button>
                <div class="collapse navbar-collapse" id="navbarNavAltMarkup">
                    <div class="navbar-nav me-auto mb-2 mb-lg-0">
                        <?php if(isLogged()) {?>
                            <a class="nav-link <?php if(str_contains($page, "gear")){ echo ("active"); }?>"  href="../gear/gears.php"><i class="fa-solid fa-bicycle"></i> <?php echo $translationsTemplateTop['template_top_navbar_gear']; ?></a>
                        <?php } ?>
                    </div>
                    <div class="navbar-nav d-flex">
                        <?php if(isLogged()) {?>
                            <span class="border-top d-sm-none d-block mb-2"></span>
                            <a class="nav-link" href="../settings/settings.php?profileSettings=1">
                                <img src="<?php if(is_null($_SESSION["photo_path"])){ if($_SESSION["gender"] == 1) { echo ("../img/avatar/farmer_avatar_male_1.png"); }else{ echo ("../img/avatar/farmer_avatar_female_1.png"); } }else{ echo ($_SESSION["photo_path"]); }?>" alt="userPhoto" width="24" height="24" class="rounded-circle"><span class="ms-2"><?php echo $translationsTemplateTop['template_top_navbar_profile']; ?></span>
                            </a>
                            <span class="border-top d-sm-none d-block mb-2"></span>
                            <a class="nav-link d-none d-sm-block">|</a>
                            <a class="nav-link" href="../settings/settings.php"><i class="fa-solid fa-gear"></i> <?php echo $translationsTemplateTop['template_top_navbar_settings']; ?></a>
                            <a class="nav-link" href="../logout.php"><i class="fas fa-sign-out-alt"></i> <?php echo $translationsTemplateTop['template_top_navbar_logout']; ?></a>
                        <?php }else{ ?> 
                            <a class="nav-link" href="../login.php"><i class="fas fa-sign-in-alt"></i> <?php echo $translationsTemplateTop['template_top_navbar_login']; ?></a>
                        <?php } ?>
                    </div>
                </div>
            </div>
        </nav>
        <div class="alert alert-warning alert-dismissible d-flex align-items-center mx-2 my-2 justify-content-center" role="alert">
            <i class="fa-solid fa-triangle-exclamation me-1"></i>
            <div>
                <span><?php echo $translationsTemplateTop['template_top_warning_zone']; ?></span> 
            </div>
        </div>