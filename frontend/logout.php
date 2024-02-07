<?php
require_once $_SERVER['DOCUMENT_ROOT'] . "/inc/sqlFunctions.php";
if (!isset($_SESSION)) {
	session_start();
}

#$response = callAPIRoute("/logout/{$_SESSION["id"]}", 1, 1, NULL);
#if ($response[0] === false) {
#	#return -1;
#} else {#
#	if ($response[1] === 200) {
		#return json_decode($response[0], true);
#	} else {
		#return -2;
#	}
#}

clearUserRelatedInfoSession();
if (isset($_GET["sessionExpired"])) {
	header("location: ../login.php?sessionExpired=1");
} else {
	header("location: ../login.php");
}
