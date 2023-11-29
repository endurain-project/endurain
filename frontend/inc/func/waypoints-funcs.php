<?php 
    /* ************************************************************************** */
    /* Waypoints                                                                  */
    /* ************************************************************************** */
    function newWaypoint($activityID, $waypoints){
        #$response = callAPIRoute("/waypoints/create/$activityID", 0, 4, array(
        #    'waypoints' => json_encode($waypoints),
        #));
        #echo json_encode($waypoints);
        $response = callAPIRoute("/waypoints/create/$activityID", 0, 4, json_encode($waypoints));
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
?>