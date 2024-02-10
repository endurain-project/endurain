<?php
/* ************************************************************************** */
/* Strava                                                                     */
/* ************************************************************************** */
/* Generate unique user state for strava link */
function setUniqueUserStateStravaLink($state)
{
    $response = callAPIRoute("/strava/set-user-unique-state/$state", 0, 3, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return 0;
        } else {
            return -2;
        }
    }
}

function unsetUniqueUserStateStravaLink()
{
    $response = callAPIRoute("/strava/unset-user-unique-state", 0, 3, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return 0;
        } else {
            return -2;
        }
    }
}

function linkStrava($state)
{
    $client_id = '115321';

    $redirect_uri = urlencode(getenv('BACKEND_PROTOCOL').'://'.getenv('BACKEND_HOST').'/strava/link');
    $scope = 'read,read_all,profile:read_all,activity:read,activity:read_all';

    $strava_auth_url = "http://www.strava.com/oauth/authorize?client_id={$client_id}&response_type=code&redirect_uri={$redirect_uri}&approval_prompt=force&scope={$scope}&state={$state}";

    
    #header("Location: " . $strava_auth_url);
    echo "<script>location.href = '$strava_auth_url';</script>";
    #<meta http-equiv="Location" content=$strava_auth_url>
}

function getStravaActivitiesLastDays($days)
{
    $response = callAPIRoute("/strava/activities/days/$days", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 202) {
            return 0;
        } else {
            return -2;
        }
    }
}

function getStravaGear()
{
    $response = callAPIRoute("/strava/gear", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 202) {
            return 0;
        } else {
            return -2;
        }
    }
}