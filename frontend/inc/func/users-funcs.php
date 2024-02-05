<?php
/* ************************************************************************** */
/* Users                                                                      */
/* ************************************************************************** */
/* Get all users */
function getUsers()
{
    $response = callAPIRoute("/users/all", 1, 0, NULL);
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

/* Get all users with pagination */
function getUsersPagination($pageNumber, $numRecords)
{
    $response = callAPIRoute("/users/all/page_number/$pageNumber/num_records/$numRecords", 1, 0, NULL);
    return parseResponse($response, 200);
}

/* Get number of users */
function numUsers()
{
    $response = callAPIRoute("/users/number", 1, 0, NULL);
    return parseResponse($response, 200);
}

/* Get user from username */
function getUserFromUsername($usernameUser)
{
    $response = callAPIRoute("/users/username/$usernameUser", 1, 0, NULL);
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

/* Get user from ID */
function getUserFromId($id)
{
    $response = callAPIRoute("/users/id/$id", 1, 0, NULL);
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

/* Get user from ID */
function getUserIdFromUsername($usernameUser)
{
    $response = callAPIRoute("/users/$usernameUser/id", 1, 0, NULL);
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

/* Get user photo path from ID */
function getUserPhotoFromID($id)
{
    $response = callAPIRoute("/users/$id/photo_path", 1, 0, NULL);
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

/* Get user photo path aux from ID */
function getUserPhotoAuxFromID($id)
{
    $response = callAPIRoute("/users/$id/photo_path_aux", 1, 0, NULL);
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

/* Creates a new user */
function newUser($name, $username, $email, $password, $gender, $preferred_language, $city, $birthdate, $access_type, $photo_path, $photo_path_aux, $is_active)
{
    if (getUserFromUsername($username) != NULL) {
        return -3;
    }

    $response = callAPIRoute("/users/create", 0, 4, json_encode(array(
        'name' => $name,
        'username' => $username,
        'email' => $email,
        'password' => hash("sha256", $password),
        'preferred_language' => $preferred_language,
        'city' => $city,
        'birthdate' => $birthdate,
        'gender' => $gender,
        'access_type' => $access_type,
        'photo_path' => $photo_path,
        'photo_path_aux' => $photo_path_aux,
        'is_active' => $is_active,
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

/* Edit user */
function editUser($name, $username, $email, $id, $preferred_language, $city, $birthdate, $gender, $access_type, $photo_path, $photo_path_aux, $is_active)
{
    $response = callAPIRoute("/users/edit", 0, 3, json_encode(array(
        'id' => $id,
        'name' => $name,
        'username' => $username,
        'email' => $email,
        'preferred_language' => $preferred_language,
        'city' => $city,
        'birthdate' => $birthdate,
        'gender' => $gender,
        'access_type' => $access_type,
        'photo_path' => $photo_path,
        'photo_path_aux' => $photo_path_aux,
        'is_active' => $is_active,
    )));
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

/* Edit user password */
function editUserPassword($user_id, $password){
    $response = callAPIRoute("/users/edit/password", 0, 3, json_encode(array(
        'id' => $user_id,
        'password' => hash("sha256", $password),
    )));
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

/* Unset user photo */
function unsetUserPhoto($id)
{
    $response = callAPIRoute("/users/$id/delete-photo", 0, 3, NULL);
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

/* Deletes a user based on its ID */
function deleteUser($id)
{
    $response = callAPIRoute("/users/$id/delete", 1, 1, NULL);
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 200) {
            return 0;
        } else {
            if ($response[1] === 409) {
                return -409;
            } else {
                return -2;
            }
        }
    }
}
