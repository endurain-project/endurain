<?php
if (!isset($_SESSION)) {
    session_start();
}

require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";

$page = "settings";

if (!isLogged()) {
    header("Location: ../login.php");
    die();
}

if (!isTokenValid($_SESSION["token"])) {
    header("Location: ../logout.php?sessionExpired=1");
    die();
}

if ($_SESSION["access_type"] != 2) {
    $_GET["profileSettings"] = 1;
}

// general
$numRecords = 5;

// Load the language file based on the user's preferred language
switch ($_SESSION["preferred_language"]) {
    case 'en':
        $translationsSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/en.php';
        break;
    case 'pt':
        $translationsSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/pt.php';
        break;
    // ...
    default:
        $translationsSettings = include $_SERVER['DOCUMENT_ROOT'] . '/lang/settings/en.php';
}
?>
<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Top.php" ?>
<div class="container mt-4">
    <div class="row row-gap-3">
        <div>
            <h1><?php echo $translationsSettings['settings_title']; ?></h1>
        </div>
        <!-- sidebar zone -->
        <div class="col-lg-4 col-md-12">
            <ul class="nav nav-pills flex-column mb-auto" id="sidebarNav">
                <?php if ($_SESSION["access_type"] == 2) { ?>
                    <li class="nav-item">
                        <a href="#" class="nav-link <?php if (!isset($_GET["profileSettings"]) && !isset($_GET["securitySettings"]) && !isset($_GET["integrationsSettings"]) && $_SESSION["access_type"] == 2) {
                            echo "text-white active";
                        }else{ echo "text-white"; } ?>" onclick="changeActive(event, 'divUsers')">
                            <i class="fa-solid fa-users me-1"></i>
                            <?php echo $translationsSettings['settings_sidebar_users']; ?>
                        </a>
                    </li>
                    <hr>
                <?php } ?>
                <li class="nav-item">
                    <a href="#" class="nav-link <?php if (isset($_GET["profileSettings"]) || ($_SESSION["access_type"] == 1 && !isset($_GET["profileSettings"]))) {
                        echo "text-white active";
                    }else{ echo "text-white"; } ?>" onclick="changeActive(event, 'divProfileSettings')">
                        <i class="fa-solid fa-address-card me-1"></i>
                        <?php echo $translationsSettings['settings_sidebar_profileSettings']; ?>
                    </a>
                </li>
                <li class="nav-item">
                    <a href="#" class="nav-link <?php if (isset($_GET["securitySettings"])) {
                        echo "text-white active";
                    }else{ echo "text-white"; } ?>" onclick="changeActive(event, 'divSecuritySettings')">
                        <i class="fa-solid fa-shield me-1"></i>
                        <?php echo $translationsSettings['settings_sidebar_securitySettings']; ?>
                    </a>
                </li>
                <li class="nav-item">
                    <a href="#" class="nav-link <?php if (isset($_GET["integrationsSettings"])) {
                        echo "text-white active";
                    }else{ echo "text-white"; } ?>" onclick="changeActive(event, 'divIntegrationsSettings')">
                        <i class="fa-solid fa-puzzle-piece me-1"></i>
                        <?php echo $translationsSettings['settings_sidebar_integrationsSettings']; ?>
                    </a>
                </li>
            </ul>
        </div>
        <hr class="d-lg-none">

        <!-- users zone -->
        <div class="col" id="divUsers" style="display: <?php if (isset($_GET["integrationsSettings"]) || isset($_GET["profileSettings"])) { echo "none"; } else { echo "block"; } ?>;">
            <?php require_once $_SERVER['DOCUMENT_ROOT'] . "/settings/inc/users-settings.php" ?>
        </div>

        <!-- profile settings zone -->
        <div class="col" id="divProfileSettings" style="display: <?php if (isset($_GET["profileSettings"])) { echo "block"; } else { echo "none"; } ?>;">
            <?php require_once $_SERVER['DOCUMENT_ROOT'] . "/settings/inc/profile-settings.php" ?>
        </div>

        <!-- security settings zone -->
        <div class="col" id="divSecuritySettings" style="display: <?php if (isset($_GET["securitySettings"])) { echo "block"; } else { echo "none"; } ?>;">
            <?php require_once $_SERVER['DOCUMENT_ROOT'] . "/settings/inc/security-settings.php" ?>
        </div>

        <!-- integrations settings zone -->
        <div class="col" id="divIntegrationsSettings" style="display: <?php if (isset($_GET["integrationsSettings"])) { echo "block"; } else { echo "none"; } ?>;">
            <?php require_once $_SERVER['DOCUMENT_ROOT'] . "/settings/inc/integration-settings.php" ?>
        </div>
    </div>
</div>

<script>
    document.addEventListener("DOMContentLoaded", function(event) {
        if (window.location.search.indexOf("users=1") !== -1) {
            changeActive(null, 'divUsers');
        }
        if (window.location.search.indexOf("profileSettings=1") !== -1) {
            changeActive(null, 'divProfileSettings');
        }
        if (window.location.search.indexOf("securitySettings=1") !== -1) {
            changeActive(null, 'divSecuritySettings');
        }
        if (window.location.search.indexOf("integrationsSettings=1") !== -1) {
            changeActive(null, 'divIntegrationsSettings');
        }
    });

    function changeActive(event, div) {
        // Prevent the default link behavior
        if (event) event.preventDefault();

        // Remove the active class from all nav items
        var navItems = document.querySelectorAll('#sidebarNav .nav-item');
        navItems.forEach(function(item) {
            if (event) item.querySelector('.nav-link').classList.remove('active');
        });

        // Add the active class to the clicked nav item
        if (event) event.target.classList.add('active');

        if (div == "divUsers") {
            document.getElementById("divUsers").style.display = 'block';
            document.getElementById("divProfileSettings").style.display = 'none';
            document.getElementById("divSecuritySettings").style.display = 'none';
            document.getElementById("divIntegrationsSettings").style.display = 'none';
        } else {
            if (div == "divProfileSettings") {
                document.getElementById("divUsers").style.display = 'none';
                document.getElementById("divProfileSettings").style.display = 'block';
                document.getElementById("divSecuritySettings").style.display = 'none';
                document.getElementById("divIntegrationsSettings").style.display = 'none';
            } else {
                if (div == "divSecuritySettings") {
                    document.getElementById("divUsers").style.display = 'none';
                    document.getElementById("divProfileSettings").style.display = 'none';
                    document.getElementById("divSecuritySettings").style.display = 'block';
                    document.getElementById("divIntegrationsSettings").style.display = 'none';
                }else{
                    if (div == "divIntegrationsSettings") {
                        document.getElementById("divUsers").style.display = 'none';
                        document.getElementById("divProfileSettings").style.display = 'none';
                        document.getElementById("divSecuritySettings").style.display = 'none';
                        document.getElementById("divIntegrationsSettings").style.display = 'block';
                    }
                }
            }
        }
    }
</script>

<?php require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/Template-Bottom.php" ?>