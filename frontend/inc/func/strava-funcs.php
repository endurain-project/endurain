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
    // Example PHP code for the authentication link
    $client_id = '115321';
    $redirect_uri = urlencode(getenv('BACKEND_PROTOCOL').'://'.getenv('BACKEND_HOST').'backend/strava/strava-callback');
    $scope = 'read,read_all,profile:read_all,activity:read,activity:read_all'; // Set your required scope

    $strava_auth_url = "http://www.strava.com/oauth/authorize?client_id={$client_id}&response_type=code&redirect_uri={$redirect_uri}&approval_prompt=force&scope={$scope}&state={$state}";

    header("Location: " . $strava_auth_url);
}

function getStravaActivities()
{
    $response = callAPIRoute("/strava/retrieve/activities", 0, 0, NULL);
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
