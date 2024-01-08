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
            return json_decode($response[0], true)["content"];
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
            return json_decode($response[0], true)["content"];
        } else {
            return -2;
        }
    }
}

/* Get user activities for provided week */
function getUserActivitiesWeek($userID, $week)
{
    $response = callAPIRoute("/activities/useractivities/$userID/week/$week", 0, 0, NULL);
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

/* Get user activities for this week */
function getUserActivitiesThisWeekDistances($userID)
{
    $response = callAPIRoute("/activities/useractivities/$userID/thisweek/distances", 0, 0, NULL);
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

/* Get user activities for this month */
function getUserActivitiesThisMonthDistances($userID)
{
    $response = callAPIRoute("/activities/useractivities/$userID/thismonth/distances", 0, 0, NULL);
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

/* Get user activities count for this month */
function getUserActivitiesThisMonthNumber($userID)
{
    $response = callAPIRoute("/activities/useractivities/$userID/thismonth/number", 0, 0, NULL);
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

/* Get all gear activities */
function getGearActivities($gearID)
{
    $response = callAPIRoute("/activities/gear/$gearID", 1, 0, NULL);
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


/* Get all activities with pagination */
function getActivitiesPagination($pageNumber, $numRecords)
{
    $response = callAPIRoute("/activities/all/pagenumber/$pageNumber/numRecords/$numRecords", 1, 0, NULL);
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

/* Get user activities with pagination */
function getUserActivitiesPagination($pageNumber, $numRecords)
{
    $response = callAPIRoute("/activities/useractivities/pagenumber/$pageNumber/numRecords/$numRecords", 1, 0, NULL);
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

/* Get user following activities with pagination */
function getFollowedUserActivitiesPagination($pageNumber, $numRecords)
{
    $response = callAPIRoute("/activities/followeduseractivities/pagenumber/$pageNumber/numRecords/$numRecords", 1, 0, NULL);
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

/* Get number of activities */
function numActivities()
{
    $response = callAPIRoute("/activities/all/number", 0, 0, NULL);
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

/* Get user number of activities */
function numUserActivities()
{
    $response = callAPIRoute("/activities/useractivities/number", 0, 0, NULL);
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

/* Get user following number of activities */
function numFollowedUserActivities()
{
    $response = callAPIRoute("/activities/followeduseractivities/number", 0, 0, NULL);
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

/* Get gear from id */
function getActivityFromId($id)
{
    $response = callAPIRoute("/activities/$id", 1, 0, NULL);
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

/* Creates a new activity */
function newActivity($distance, $name, $type, $starttime, $endtime, $town, $country, $city, $elevationGain, $elevationLoss, $pace, $averageSpeed, $averagePower, $strava_id)
{
    $response = callAPIRoute("/activities/create", 0, 4, json_encode(array(
        'distance' => $distance,
        'name' => $name,
        'activity_type' => $type,
        'start_time' => $starttime,
        'end_time' => $endtime,
        'city' => $city,
        'town' => $town,
        'country' => $country,
        'elevation_gain' => $elevationGain,
        'elevation_loss' => $elevationLoss,
        'pace' => $pace,
        'average_speed' => $averageSpeed,
        'average_power' => $averagePower,
        'strava_activity_id' => $strava_id,
    )));
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === 201) {
            return json_decode($response[0], true)["activity_id"];
            // $data = json_decode($response[0], true);
            // if (isset($data['id'])) {
            //     return $data['id']; // Return the activity ID.
            // } else {
            //     return -2; // Response doesn't contain the ID.
            // }
        } else {
            return -2;
        }
    }
}

function parseActivityGPX($gpx_file)
{
    try {
        $xml = simplexml_load_file($gpx_file);
        if ($xml === false) {
            throw new Exception("Invalid GPX file or could not load the file.");
        }

        if ((string) $xml['creator'] != 'StravaGPX' && (string) $xml['creator'] != 'Garmin Connect') {
            return -5;
        }

        // Extract metadata
        $activityType = (string) ($xml->trk->type ?? "Workout"); // Extract activity type
        $activityName = (string) ($xml->trk->name ?? "Workout"); // Extract activity name
        $distance = 0;  // Initialize total distance to 0
        $firstWaypointTime = null;  // Variable to store the first waypoint time
        $lastWaypointTime = null;   // Variable to store the last waypoint time
        $city = null;   // Variable to store the last waypoint time
        $town = null;   // Variable to store the last waypoint time
        $country = null;   // Variable to store the last waypoint time
        $processOneTimeFields = 0;
        $elevationGain = 0;
        $elevationLoss = 0;
        $pace = 0;
        // Extract the start time from metadata
        #$startTime = (string)$xml->metadata->time;

        $waypoints = [];
        $prevLatitude = null;
        $prevLongitude = null;

        // Iterate through track segments and track points
        foreach ($xml->trk->trkseg->trkpt as $point) {
            $latitude = (float) $point['lat'];
            $longitude = (float) $point['lon'];

            if ($prevLatitude !== null && $prevLongitude !== null) {
                // Calculate distance between waypoints (Haversine formula) and add to total distance
                $distance += calculateDistance($prevLatitude, $prevLongitude, $latitude, $longitude);
            }

            $elevation = (float) $point->ele;

            // You can access other data like time, heart rate, cadence, etc. from the extensions as needed
            $time = (string) $point->time;
            // Store the first and last waypoint times
            if ($firstWaypointTime === null) {
                $firstWaypointTime = $time;
            }

            // Store the town and country
            if ($processOneTimeFields == 0) {
                $url = "https://geocode.maps.co/reverse?lat=$latitude&lon=$longitude";
                $ch = curl_init($url);
                curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
                try {
                    $response = curl_exec($ch);
                    #echo $response;
                    if ($response !== false) {
                        // Parse the JSON response
                        $data = json_decode($response);
                        #echo $data;
                        // Extract the town and country from the address components
                        if (isset($data->address->city)) {
                            $city = (string) $data->address->city;
                        }
                        if (isset($data->address->town)) {
                            $town = (string) $data->address->town;
                        }
                        if (isset($data->address->country)) {
                            $country = (string) $data->address->country;
                        }
                    }
                } catch (Exception $e) {
                    echo "An error occurred: " . $e->getMessage();
                }
                curl_close($ch);
                $processOneTimeFields = 1;
            }

            if ((string) $xml['creator'] === 'StravaGPX') {
                $heartRate = (int) $point->extensions->children('gpxtpx', true)->TrackPointExtension->hr;
                $cadence = (int) $point->extensions->children('gpxtpx', true)->TrackPointExtension->cad;
            } else {
                $heartRate = (int) $point->extensions->children('ns3', true)->TrackPointExtension->hr;
                $cadence = (int) $point->extensions->children('ns3', true)->TrackPointExtension->cad;
            }
            $power = (int) $point->extensions->power;

            $instantSpeed = (float) calculateInstantSpeed($lastWaypointTime, $time, $latitude, $longitude, $prevLatitude, $prevLongitude);

            if ($instantSpeed > 0) {
                $instantPace = 1 / $instantSpeed; // Calculate instant pace in s/m
            } else {
                $instantPace = 0; // Avoid division by zero for points with zero speed
            }

            // $waypoints[] = [
            //     'lat' => $latitude,
            //     'lon' => $longitude,
            //     'ele' => $elevation,
            //     'time' => $time,
            //     'hr' => $heartRate,
            //     'cad' => $cadence,
            //     'power' => $power,
            //     'vel' => $instantSpeed,
            //     'pace' => $instantPace,
            // ];
            if(isset($latitude) && isset($longitude)){
                $latLonWaypoints[] = [
                    'time' => $time,
                    'lat' => $latitude,
                    'lon' => $longitude,
                ];
            }
            if(isset($elevation)){
                $eleWaypoints[] = [
                    'time' => $time,
                    'ele' => $elevation,
                ];
            }
            if(isset($heartRate)){
                $hrWaypoints[] = [
                    'time' => $time,
                    'hr' => $heartRate,
                ];
            }
            if(isset($cadence)){
                $cadWaypoints[] = [
                    'time' => $time,
                    'cad' => $cadence,
                ];
            }
            if(isset($power)){
                $powerWaypoints[] = [
                    'time' => $time,
                    'power' => $power,
                ];
            }
            if(isset($instantSpeed) && $instantSpeed != 0){
                $velWaypoints[] = [
                    'time' => $time,
                    'vel' => $instantSpeed,
                ];
            }
            if($instantPace != 0){
                $paceWaypoints[] = [
                    'time' => $time,
                    'pace' => $instantPace,
                ];
            }

            // Update previous latitude and longitude for the next iteration
            $prevLatitude = $latitude;
            $prevLongitude = $longitude;
            $lastWaypointTime = $time;
        }

        $elevationData = calculateElevationGainLoss($eleWaypoints);
        $elevationGain = $elevationData['elevationGain'];
        $elevationLoss = $elevationData['elevationLoss'];
        $pace = calculatePace($distance, $firstWaypointTime, $lastWaypointTime);

        $averageSpeed = calculateAverageSpeed($distance, $firstWaypointTime, $lastWaypointTime);

        $averagePower = calculateAveragePower($powerWaypoints);

        $newActivityresult = newActivity(intval(number_format($distance, 0, '', '')), $activityName, $activityType, $firstWaypointTime, $lastWaypointTime, $town, $country, $city, $elevationGain, $elevationLoss, number_format($pace, 10), number_format($averageSpeed, 10), $averagePower, null);
        if($newActivityresult > 0){
            $auxResultStreams = 0;
            if($hrWaypoints != null){
                $hrStreamResult = newActivityStream($newActivityresult, 1, $hrWaypoints, null);
                if($hrStreamResult != 0){
                    $auxResultStreams = -5;
                }
            }
            if($powerWaypoints != null){
                $powerStreamResult = newActivityStream($newActivityresult, 2, $powerWaypoints, null); 
                if($powerStreamResult != 0){
                    $auxResultStreams = -6;
                }
            }
            if($cadWaypoints != null){
                $cadStreamResult = newActivityStream($newActivityresult, 3, $cadWaypoints, null); 
                if($cadStreamResult != 0){
                    $auxResultStreams = -7;
                }
            }
            if($eleWaypoints != null){
                $eleStreamResult = newActivityStream($newActivityresult, 4, $eleWaypoints, null); 
                if($eleStreamResult != 0){
                    $auxResultStreams = -8;
                }
            }
            if($velWaypoints != null){
                $velStreamResult = newActivityStream($newActivityresult, 5, $velWaypoints, null); 
                if($velStreamResult != 0){
                    $auxResultStreams = -9;
                }
            }
            if($paceWaypoints != null){
                $paceStreamResult = newActivityStream($newActivityresult, 6, $paceWaypoints, null); 
                if($paceStreamResult != 0){
                    $auxResultStreams = -10;
                }
            }
            if($latLonWaypoints != null){
                $latLonStreamResult = newActivityStream($newActivityresult, 7, $latLonWaypoints, null); 
                if($latLonStreamResult != 0){
                    $auxResultStreams = -11;
                }
            }
            return $auxResultStreams;
        }else{
            return $newActivityresult;
        }
        #return newActivity(intval(number_format($distance, 0, '', '')), $activityName, $activityType, $firstWaypointTime, $lastWaypointTime, $town, $country, $city, $waypoints, $elevationGain, $elevationLoss, number_format($pace, 10), number_format($averageSpeed, 10), $averagePower, null);
    } catch (Exception $e) {
        // Handle the exception
        #echo "Error: " . $e->getMessage();
        // You can log the error, redirect the user, or take appropriate action.
        return -4;
    }
}

// Function to calculate distance
function calculateDistance($lat1, $lon1, $lat2, $lon2)
{
    // The radius of the Earth in meters (mean value)
    $earthRadius = 6371000; // 6,371 km = 6,371,000 meters

    // Convert latitude and longitude from degrees to radians
    $lat1 = deg2rad($lat1);
    $lon1 = deg2rad($lon1);
    $lat2 = deg2rad($lat2);
    $lon2 = deg2rad($lon2);

    // Haversine formula
    $latDiff = $lat2 - $lat1;
    $lonDiff = $lon2 - $lon1;
    $a = sin($latDiff / 2) * sin($latDiff / 2) + cos($lat1) * cos($lat2) * sin($lonDiff / 2) * sin($lonDiff / 2);
    $c = 2 * atan2(sqrt($a), sqrt(1 - $a));
    $distance = $earthRadius * $c;

    return $distance;
}

// Add this function to calculate elevation gain and loss
function calculateElevationGainLoss($waypoints)
{
    $elevationGain = 0;
    $elevationLoss = 0;
    $prevElevation = null;

    foreach ($waypoints as $waypoint) {
        $elevation = $waypoint['ele'];

        if ($prevElevation !== null) {
            $elevationChange = $elevation - $prevElevation;
            if ($elevationChange > 0) {
                $elevationGain += $elevationChange;
            } else {
                $elevationLoss -= $elevationChange;
            }
        }

        $prevElevation = $elevation;
    }

    return ['elevationGain' => $elevationGain, 'elevationLoss' => $elevationLoss];
}

// Add this function to calculate pace
function calculatePace($distance, $firstWaypointTime, $lastWaypointTime)
{
    // Convert the time strings to DateTime objects
    $startDateTime = new DateTime($firstWaypointTime);
    $endDateTime = new DateTime($lastWaypointTime);

    // Calculate the time difference in seconds
    $totalTimeInSeconds = $endDateTime->getTimestamp() - $startDateTime->getTimestamp();

    // Calculate pace in seconds per meter
    $paceInSecondsPerMeter = $totalTimeInSeconds / $distance;
    return $paceInSecondsPerMeter;
}

function calculateInstantSpeed($prevTime, $time, $latitude, $longitude, $prevLatitude, $prevLongitude)
{
    $timeCalc = new DateTime($time);
    if ($prevTime !== null) {
        $prevTimeCalc = new DateTime($prevTime);
    } else {
        return 0; // Return a default value when $prevTime is null
    }

    $instantSpeed = 0; // Initialize $instantSpeed

    if ($prevTimeCalc !== null) {
        $timeDifference = $timeCalc->getTimestamp() - $prevTimeCalc->getTimestamp();
        if ($timeDifference > 0) {
            $distance = calculateDistance($prevLatitude, $prevLongitude, $latitude, $longitude);
            $instantSpeed = $distance / $timeDifference;
        }
    }

    return $instantSpeed; // output in m/s
}

function calculateAverageSpeed($distance, $firstWaypointTime, $lastWaypointTime)
{
    // Convert the time strings to DateTime objects
    $startDateTime = new DateTime($firstWaypointTime);
    $endDateTime = new DateTime($lastWaypointTime);

    // Calculate the time difference in seconds
    $totalTimeInSeconds = $endDateTime->getTimestamp() - $startDateTime->getTimestamp();

    // Calculate average speed in meters per second
    $averageSpeed = $distance / $totalTimeInSeconds;

    return $averageSpeed;
}

function calculateAveragePower($waypoints)
{
    $totalPower = 0;
    $numDataPoints = count($waypoints);

    foreach ($waypoints as $waypoint) {
        $totalPower += $waypoint['power'];
    }

    if ($numDataPoints > 0) {
        $averagePower = $totalPower / $numDataPoints;
        return $averagePower;
    } else {
        return 0; // Avoid division by zero in case of no data points
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
