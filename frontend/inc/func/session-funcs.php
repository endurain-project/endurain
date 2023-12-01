<?php 
    /* ************************************************************************** */
    /* Session info                                                               */
    /* ************************************************************************** */

    /* Check if a user is logged */
    function isLogged(){
        if (isset($_SESSION["id"])){
            if ($_SESSION["id"]>=0){
                return TRUE;
            }
        }
        return FALSE;
    }

    /* Check if user token is valid */
    function isTokenValid($token){
        $response = callAPIRoute("/validate_token", 1, 0, NULL);
        if ($response[0] === false) {
            return -1;
        } else {
            if ($response[1] === 200) {
                $data = json_decode($response[0], true);
                if (isset($data["message"]) && $data["message"] === "Token is valid") {
                    return true;
                } else {
                    return false;
                }
            } else {
                return false;
            }
        }
    }

    /* Do a login */
    function loginUser($username, $password, $neverExpires){
        $response = callAPIRoute("/token", 0, 5, json_encode(array(
            'username' => $username,
            'password' => $password,
            'neverExpires' => $neverExpires,
        )));
        return $response[0];
    }
    

    /* Unset user info */
    function clearUserRelatedInfoSession(){
        unset($_SESSION["token"]);
        unset($_SESSION["id"]);
        unset($_SESSION["username"]);
        unset($_SESSION["email"]);
        unset($_SESSION["name"]);
        unset($_SESSION["city"]);
        unset($_SESSION["birthdate"]);
        unset($_SESSION["preferred_language"]);
        unset($_SESSION["gender"]);
        unset($_SESSION["access_type"]);
        unset($_SESSION["photo_path"]);
        unset($_SESSION["photo_path_aux"]);
    }

    /* Set user info */
    function setUserRelatedInfoSession($token){
        clearUserRelatedInfoSession();

        $_SESSION["token"] = $token;

        $response = callAPIRoute("/users/me", 1, 0, NULL);
        if ($response[0] === false) {
            return -1;
        } else {
            if ($response[1] === 200) {
                $user = json_decode($response[0], true);
                if($user['is_active'] == 0){
                    clearUserRelatedInfoSession();
                    return -3;
                }
                // Populate the $_SESSION variable with user information
                // $_SESSION["token"] = $token;
                $_SESSION["id"] = $user['id'];
                $_SESSION["name"] = $user['name'];
                $_SESSION["username"] = $user['username'];
                $_SESSION["email"] = $user['email'];
                $_SESSION["city"] = $user['city'];
                #$_SESSION["birthdate"] = date("d/m/Y", strtotime($user['birthdate']));
                $_SESSION["birthdate"] = $user['birthdate'];
                $_SESSION["preferred_language"] = $user['preferred_language'];
                $_SESSION["gender"] = $user['gender'];
                $_SESSION["access_type"] = $user['access_type'];
                $_SESSION["photo_path"] = $user['photo_path'];
                $_SESSION["photo_path_aux"] = $user['photo_path_aux'];
                $_SESSION["is_strava_linked"] = $user['is_strava_linked'];
                return 0;
            } else {
                return -2;
            }
        }
    }