<?php 
    /* ************************************************************************** */
    /* Main API Funcs                                                             */
    /* ************************************************************************** */
    /* Get to call a API route */
    function callAPIRoute($endpoint, $multipleReturns, $callType, $dataFields){
        $api_url = 'http://backend';
        $responseArray = [];

        // Initialize a new cURL session
        $ch = curl_init();
        // Set the cURL options to make an HTTP GET request to the API endpoint with an OAuth2 bearer token in the Authorization header
        curl_setopt($ch, CURLOPT_URL, $api_url . $endpoint);

        // 0 GET, 1 DELETE, 2 POST, 3 PUT
        if($callType == 1){
            curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "DELETE");
        }else{
            if($callType == 2){
                curl_setopt($ch, CURLOPT_POST, true);
                if($dataFields != NULL){           
                    curl_setopt($ch, CURLOPT_POSTFIELDS, http_build_query($dataFields));
                }
            }else{
                if($callType == 3){
                    curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "PUT");
                    if($dataFields != NULL){ 
                        curl_setopt($ch, CURLOPT_POSTFIELDS, $dataFields);
                    }
                }else{
                    if($callType == 4 || $callType == 5){
                        curl_setopt($ch, CURLOPT_POST, true);
                        if($dataFields != NULL){     
                            // Set the Content-Type header to specify JSON data      
                            #curl_setopt($ch, CURLOPT_HTTPHEADER, array(
                            #    'Content-Type: application/json'
                            #));
                            curl_setopt($ch, CURLOPT_POSTFIELDS, $dataFields);
                        }
                    }
                }
            }
        }

        if($multipleReturns == 1){
            curl_setopt($ch, CURLOPT_HTTPHEADER, array(
                "Authorization: Bearer {$_SESSION["token"]}"
            ));
        }else{
            if($callType == 4 || $callType == 3){
                curl_setopt($ch, CURLOPT_HTTPHEADER, array(
                    "Content-Type: application/json",
                    "Authorization: Bearer {$_SESSION["token"]}"
                ));
            }else{
                if($callType == 5){
                    curl_setopt($ch, CURLOPT_HTTPHEADER, array(
                        "Content-Type: application/json"
                    ));
                }else{
                    curl_setopt($ch, CURLOPT_HTTPHEADER, [
                        "Authorization: Bearer {$_SESSION["token"]}"
                    ]);
                }
            }
        }
        
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        // Execute the cURL request and store the response in a variable
        $response = curl_exec($ch);

        $responseArray[] = $response;
        $responseArray[] = curl_getinfo($ch, CURLINFO_HTTP_CODE);

        #echo $responseArray[0]." + ".$responseArray[1];

        curl_close($ch);

        return $responseArray;
    }