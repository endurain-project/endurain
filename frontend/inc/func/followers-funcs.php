<?php
/* ************************************************************************** */
/* Followers                                                                  */
/* ************************************************************************** */
/* Get if user follows specific user */
function getStatusUserFollowsSpecificUser($user_id)
{
    $response = callAPIRoute("/followers/user/".$_SESSION["id"]."/targetUser/$user_id", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Get user followers count all */
function getUserFollowersCountAll($user_id)
{
    $response = callAPIRoute("/followers/user/$user_id/followers/count/all", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Get user followers count */
function getUserFollowersCount($user_id)
{
    $response = callAPIRoute("/followers/user/$user_id/followers/count", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Get user followers all */
function getUserFollowersAll($user_id)
{
    $response = callAPIRoute("/followers/user/$user_id/followers/all", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Get user following count all */
function getUserFollowingCountAll($user_id)
{
    $response = callAPIRoute("/followers/user/$user_id/following/count/all", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Get user following count */
function getUserFollowingCount($user_id)
{
    $response = callAPIRoute("/followers/user/$user_id/following/count", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Get user following all */
function getUserFollowingAll($user_id)
{
    $response = callAPIRoute("/followers/user/$user_id/following/all", 0, 0, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Accept user follows specific user */
function acceptUserFollowsSpecificUser($user_id, $taget_user_id)
{
    $response = callAPIRoute("/followers/accept/user/$user_id/targetUser/$taget_user_id", 0, 3, NULL);
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

/* Create user follows specific user */
function createUserFollowsSpecificUser($user_id)
{
    $response = callAPIRoute("/followers/create/user/".$_SESSION["id"]."/targetUser/$user_id", 0, 2, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 201) {
            return json_decode($response[0], true);
        } else {
            return -2;
        }
    }
}

function deleteUserFollowsSpecificUser($user_id, $taget_user_id)
{
    $response = callAPIRoute("/followers/delete/user/$user_id/targetUser/$taget_user_id", 0, 1, NULL);
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