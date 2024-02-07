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
    $response = callAPIRoute("/activities/user", 1, 0, NULL);
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
    $response = callAPIRoute("/activities/user/$userID/week/$week", 1, 0, NULL);
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
    $response = callAPIRoute("/activities/user/$userID/thisweek/distances", 1, 0, NULL);
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
    $response = callAPIRoute("/activities/user/$userID/thismonth/distances", 1, 0, NULL);
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
    $response = callAPIRoute("/activities/user/$userID/thismonth/number", 1, 0, NULL);
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
function getGearActivities($user_id, $gearID)
{
    $response = callAPIRoute("/activities/user/$user_id/gear/$gearID", 1, 0, NULL);
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
    $response = callAPIRoute("/activities/user/$userID/page_number/$pageNumber/num_records/$numRecords", 1, 0, NULL);
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
function getFollowedUserActivitiesPagination($user_id, $pageNumber, $numRecords)
{
    $response = callAPIRoute("/activities/user/$user_id/followed/page_number/$pageNumber/num_records/$numRecords", 1, 0, NULL);
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
    $response = callAPIRoute("/activities/user/$userID/number", 1, 0, NULL);
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
function numFollowedUserActivities($user_id)
{
    $response = callAPIRoute("/activities/user/$user_id/followed/number", 1, 0, NULL);
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
function uploadActivityFile($user_id, $file)
{
    $response = callAPIRoute("/activities/$user_id/create/upload", 1, 6, $file);
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
    $response = callAPIRoute("/activities/$id/delete", 1, 1, NULL);
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