<?php
/* ************************************************************************** */
/* Main API Funcs                                                             */
/* ************************************************************************** */
/* Get to call a API route */
function callAPIRoute($endpoint, $multipleReturns, $callType, $dataFields)
{
    $api_url = getenv('BACKEND_PROTOCOL').'://'.getenv('BACKEND_HOST');
    $responseArray = [];

    // Initialize a new cURL session
    $ch = curl_init();

    // Set the cURL options to make an HTTP GET request to the API endpoint with an OAuth2 bearer token in the Authorization header
    curl_setopt($ch, CURLOPT_URL, $api_url . $endpoint);

    // 0 GET, 1 DELETE, 2 POST, 3 PUT, 4 and 5 POST with $dataFields already JSON Encoded, 6 POST that will send a file
    if ($callType == 1) {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "DELETE");
    } else {
        if ($callType == 2) {
            curl_setopt($ch, CURLOPT_POST, true);
            if ($dataFields != NULL) {
                curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($dataFields));
            }
        } else {
            if ($callType == 3) {
                curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
                if ($dataFields != NULL) {
                    curl_setopt($ch, CURLOPT_POSTFIELDS, $dataFields);
                }
            } else {
                if ($callType == 4 || $callType == 5) {
                    curl_setopt($ch, CURLOPT_POST, true);
                    if ($dataFields != NULL) {
                        curl_setopt($ch, CURLOPT_POSTFIELDS, $dataFields);
                    }
                }else{
                    if ($callType == 6) {
                        curl_setopt($ch, CURLOPT_POST, true);
                        if ($dataFields != NULL) {
                            $fileField = 'file';
                            curl_setopt($ch, CURLOPT_POSTFIELDS, [
                                $fileField => new CURLFile($dataFields),
                            ]);
                        }
                    }
                }
            }
        }
    }

    if ($multipleReturns == 1) {
        curl_setopt($ch, CURLOPT_HTTPHEADER, array(
            "Authorization: Bearer {$_SESSION["token"]}"
        ));
    } else {
        if ($callType == 4 || $callType == 3) {
            curl_setopt($ch, CURLOPT_HTTPHEADER, array(
                "Content-Type: application/json",
                "Authorization: Bearer {$_SESSION["token"]}"
            ));
        } else {
            if ($callType == 5) {
                curl_setopt($ch, CURLOPT_HTTPHEADER, array(
                    "Content-Type: application/json"
                ));
            } else {
                curl_setopt($ch, CURLOPT_HTTPHEADER, array(
                    "Content-Type: application/x-www-form-urlencoded"
                ));
            }
        }
    }

    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    // Execute the cURL request and store the response in a variable
    $response = curl_exec($ch);

    $responseArray[] = $response;
    $responseArray[] = curl_getinfo($ch, CURLINFO_HTTP_CODE);

    curl_close($ch);

    return $responseArray;
}

function parseResponse($response, $success_code)
{
    if ($response[0] === false) {
        return -1;
    } else {
        if ($response[1] === $success_code) {
            return json_decode($response[0], true);
        } else {
            if ($response[1] === 401) {
                if (json_decode($response[0], true)["detail"] === "Token no longer valid"){
                    #clearUserRelatedInfoSession();
                    #header("location: ../logout.php?sessionExpired=1");
                }
            }else{
                if ($response[1] === 403) {
                    return -2;
                }else{
                    if ($response[1] === 409) {
                        #return {
                        #    "error_code" => $response[1], 
                        #    "error_message" => json_decode($response[0], true)["detail"],
                        #};
                    }else{
                        return -2;
                    }
                }
            }
        }
    }
}