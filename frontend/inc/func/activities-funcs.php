<?php
/* ************************************************************************** */
/* Activies                                                                   */
/* ************************************************************************** */
/* Get all activities */
function getActivities()
{
    $response = callAPIRoute("/activities/all", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user activities */
function getUserActivities()
{
    $response = callAPIRoute("/activities/useractivities", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user activities for provided week */
function getUserActivitiesWeek($userID, $week)
{
    $response = callAPIRoute("/activities/$userID/week/$week", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user activities for this week */
function getUserActivitiesThisWeekDistances($userID)
{
    $response = callAPIRoute("/activities/$userID/thisweek/distances", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user activities for this month */
function getUserActivitiesThisMonthDistances($userID)
{
    $response = callAPIRoute("/activities/$userID/thismonth/distances", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user activities count for this month */
function getUserActivitiesThisMonthNumber($userID)
{
    $response = callAPIRoute("/activities/$userID/thismonth/number", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get all gear activities */
function getGearActivities($gearID)
{
    $response = callAPIRoute("/activities/gear/$gearID", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}


/* Get all activities with pagination */
function getActivitiesPagination($pageNumber, $numRecords)
{
    $response = callAPIRoute("/activities/all/pagenumber/$pageNumber/numRecords/$numRecords", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user activities with pagination */
function getUserActivitiesPagination($userID, $pageNumber, $numRecords)
{
    $response = callAPIRoute("/activities/$userID/page_number/$pageNumber/num_records/$numRecords", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user following activities with pagination */
function getFollowedUserActivitiesPagination($pageNumber, $numRecords)
{
    $response = callAPIRoute("/activities/followeduseractivities/page_number/$pageNumber/num_records/$numRecords", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get number of activities */
function numActivities()
{
    $response = callAPIRoute("/activities/all/number", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user number of activities */
function numUserActivities($userID)
{
    $response = callAPIRoute("/activities/$userID/number", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get user following number of activities */
function numFollowedUserActivities()
{
    $response = callAPIRoute("/activities/followeduseractivities/number", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

/* Get gear from id */
function getActivityFromId($id)
{
    $response = callAPIRoute("/activities/$id", 1, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}
/* adds gear_id to activity */
function addGearToActivity($activityID, $gearID)
{
    $response = callAPIRoute("/activities/$activityID/addgear/$gearID", 0, 3, NULL);
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

/* Uploads activity file */
function uploadActivityFile($file)
{
    $response = callAPIRoute("/activities/create/upload", 0, 6, $file);
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

/* Unset activity gear */
function unsetActivityGear($id)
{
    $response = callAPIRoute("/activities/$id/deletegear", 0, 3, NULL);
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

/* Deletes an activity based on its ID */
function deleteActivity($id)
{
    $response = callAPIRoute("/activities/$id/delete", 0, 1, NULL);
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