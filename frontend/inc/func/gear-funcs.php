<?php
/* ************************************************************************** */
/* Gear                                                                       */
/* ************************************************************************** */
/* Get all gear */
function getGear()
{
    $response = callAPIRoute("/gear/all", 1, 0, NULL);
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

/* Get all gear from type*/
function getGearFromType($gear_type)
{
    $response = callAPIRoute("/gear/type/$gear_type", 1, 0, NULL);
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

/* Get all gear with pagination */
function getGearPagination($pageNumber, $numRecords)
{
    $response = callAPIRoute("/gear/page_number/$pageNumber/num_records/$numRecords", 1, 0, NULL);
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

/* Get number of gear */
function numGears()
{
    $response = callAPIRoute("/gear/number", 1, 0, NULL);
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

/* Get gear from nickname */
function getGearFromNickname($nickname)
{
    $response = callAPIRoute("/gear/nickname/$nickname", 1, 0, NULL);
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
function getGearFromId($gear_id)
{
    $response = callAPIRoute("/gear/id/$gear_id", 1, 0, NULL);
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

/* Creates a new gear */
function newGear($brand, $model, $nickname, $gear_type, $date)
{
    #if (getGearFromNickname($nickname) != NULL) {
    #    return -3;
    #}

    $response = callAPIRoute("/gear/create", 0, 4, json_encode(array(
        'brand' => $brand,
        'model' => $model,
        'nickname' => $nickname,
        'gear_type' => $gear_type,
        'created_at' => $date,
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

/* Edit gear */
function editGear($id, $brand, $model, $nickname, $gear_type, $date, $is_active)
{
    $response = callAPIRoute("/gear/$id/edit", 0, 3, json_encode(array(
        'brand' => $brand,
        'model' => $model,
        'nickname' => $nickname,
        'gear_type' => $gear_type,
        'date' => $date,
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

/* Deletes a gear based on its ID */
function deleteGear($id)
{
    $response = callAPIRoute("/gear/$id/delete", 1, 1, NULL);
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
