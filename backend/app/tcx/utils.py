"""
Parsing logic for TCX files. Tested specifically with the TCX files produced by the Polar Flow application.
"""
import tcxreader
import activities.activity.schema as activities_schema


def parse_tcx_file(file, user_id, user_privacy_settings, db):
    tcx_file = tcxreader.TCXReader().read(file)
    trackpoints = tcx_file.trackpoints_to_dict()

    lat_lon_waypoints = [{'time': trackpoint['time'].strftime("%Y-%m-%dT%H:%M:%S"),
                          'lat': trackpoint['latitude'],
                          'lon': trackpoint['longitude']}
                         for trackpoint in trackpoints]
    distance = tcx_file.distance

    activity = activities_schema.Activity(
        user_id=user_id,
        name=tcx_file.activity_type,
        distance=round(distance) if distance else 0,
        activity_type=1,
        start_time=tcx_file.start_time.strftime("%Y-%m-%dT%H:%M:%S"),
        end_time=tcx_file.end_time.strftime("%Y-%m-%dT%H:%M:%S"),
        total_elapsed_time=(tcx_file.end_time - tcx_file.start_time).total_seconds(),
        total_timer_time=(tcx_file.end_time - tcx_file.start_time).total_seconds(),
        hide_start_time=user_privacy_settings.hide_activity_start_time or False,
        hide_location=user_privacy_settings.hide_activity_location or False,
        hide_map=user_privacy_settings.hide_activity_map or False,
        hide_hr=user_privacy_settings.hide_activity_hr or False,
        hide_power=user_privacy_settings.hide_activity_power or False,
        hide_cadence=user_privacy_settings.hide_activity_cadence or False,
        hide_elevation=user_privacy_settings.hide_activity_elevation or False,
        hide_speed=user_privacy_settings.hide_activity_speed or False,
        hide_pace=user_privacy_settings.hide_activity_pace or False,
        hide_laps=user_privacy_settings.hide_activity_laps or False,
        hide_workout_sets_steps=user_privacy_settings.hide_activity_workout_sets_steps
                                or False,
        hide_gear=user_privacy_settings.hide_activity_gear or False,
    )

    laps = [{
        "start_time": lap.start_time,
        "start_position_lat": lap.trackpoints[0].latitude,
        "start_position_long": lap.trackpoints[0].longitude,
        "end_position_lat": lap.trackpoints[-1].latitude,
        "end_position_long": lap.trackpoints[-1].longitude,
    } for lap in tcx_file.laps]

    hr_waypoints = [{'time': trackpoint['time'].strftime("%Y-%m-%dT%H:%M:%S"),
                     'hr': trackpoint['hr_value']}
                    for trackpoint in trackpoints
                    if 'hr_value' in trackpoint]
    vel_waypoints = []
    pace_waypoints = []
    cad_waypoints = [{'time': trackpoint['time'].strftime("%Y-%m-%dT%H:%M:%S"),
                      'cad': trackpoint['cadence']}
                     for trackpoint in trackpoints
                     if 'cadence' in trackpoint]
    ele_waypoints = [{'time': trackpoint['time'].strftime("%Y-%m-%dT%H:%M:%S"),
                      'ele': trackpoint['elevation']}
                     for trackpoint in trackpoints
                     if 'elevation' in trackpoint]
    power_waypoints = [{'time': trackpoint['time'].strftime("%Y-%m-%dT%H:%M:%S"),
                        'power': trackpoint.tpx_ext['Watts']}
                       for trackpoint in trackpoints
                       if hasattr(trackpoint, 'tpx_ext')
                       and 'Watts' in trackpoint.tpx_ext]

    return {
        "activity": activity,
        "is_elevation_set": bool(ele_waypoints),
        "ele_waypoints": ele_waypoints,
        "is_power_set": bool(power_waypoints),
        "power_waypoints": power_waypoints,
        "is_heart_rate_set": bool(hr_waypoints),
        "hr_waypoints": hr_waypoints,
        "is_velocity_set": bool(vel_waypoints),
        "vel_waypoints": vel_waypoints,
        "pace_waypoints": pace_waypoints,
        "is_cadence_set": bool(cad_waypoints),
        "cad_waypoints": cad_waypoints,
        "is_lat_lon_set": bool(lat_lon_waypoints),
        "lat_lon_waypoints": lat_lon_waypoints,
        "laps": laps,
    }
