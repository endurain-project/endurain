<?php
/* ************************************************************************** */
/* Activies streams                                                           */
/* ************************************************************************** */
/* Get all activity activity streams */
function getActivityActivitiesStream($activity_id)
{
    $response = callAPIRoute("/activities/streams/activity_id/$activity_id/all", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            #echo $response[0];
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Creates a new activity stream */
function newActivityStream($activity_id, $stream_type, $stream_waypoints, $strava_activity_stream_id)
{
    $response = callAPIRoute("/activities/streams/create", 0, 4, json_encode(array(
        'activity_id' => $activity_id,
        'stream_type' => $stream_type,
        'stream_waypoints' => $stream_waypoints,
        'strava_activity_stream_id' => $strava_activity_stream_id,
    )));
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 201) {
            return 0;
        } else {
            return -2;
        }
    }
}