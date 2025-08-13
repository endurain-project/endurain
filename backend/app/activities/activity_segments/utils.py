import activities.activity_segments.schema as segments_schema
import activities.activity_segments.models as segments_models
import activities.activity_streams.models as streams_models
import activities.activity_streams.crud as streams_crud
import activities.activity.models as activity_models
import activities.activity.crud as activity_crud
import activities.activity.utils as activity_utils
from shapely.geometry import Point, LineString, MultiPoint
from datetime import datetime
from zoneinfo import ZoneInfo
from geopy.distance import geodesic
from sqlalchemy.orm import Session
import core.logger as core_logger
import statistics
import os

def distance_between_points(point1: Point, point2: Point) -> float:
    # Returns the distance between two points.
    return geodesic((point1.x, point1.y), (point2.x, point2.y)).meters

def calculate_distance(points):
    distance = 0
    prev_point = None
    for point in points:
        
        if prev_point is not None:
            distance += distance_between_points(prev_point, point)

        prev_point = point
    return distance

def date_convert_timezone(date: datetime, timezone: str):
    def make_aware_and_format(dt, timezone):
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(timezone).strftime("%Y-%m-%dT%H:%M:%S")

    timezone = (
        ZoneInfo(timezone)
        if timezone
        else ZoneInfo(os.environ.get("TZ", "UTC"))
    )

    return make_aware_and_format(date, timezone)

def find_repeating_pattern_valid(lst):
    n = len(lst)
    for size in range(2, n // 2 + 1):
        for i in range(0, n - size):
            pattern = lst[i:i+size]
            # Check if pattern is valid
            if pattern[0] == 0 and pattern[-1] == max(lst):
                count = 0
                for j in range(0, len(lst)-size+1):
                    match = lst[j:j+size]
                    if pattern == match:
                        count += 1
                if count > 1:
                    return pattern
                else:
                    return None

def intersections_to_db_mapping(intersections, 
                                activity: activity_models.Activity, 
                                segment: segments_models.Segments
                                ):
    segment_mappings = []
#    core_logger.print_to_log(intersections)
    if intersections:
        for i in range(len(intersections['lap_number'])):
            db_mapping = {
                'activity_id': activity.id,
                'segment_id': segment.id,
                'segment_name': segment.name.strip(),
                'segment_distance': round(intersections['segment_distance'][i]),
                'segment_time': intersections['segment_times'][i],
                'segment_pace': intersections['segment_pace'][i],
                'segment_hr_avg': intersections['segment_avg_hr'][i],
                'segment_hr_max': intersections['segment_max_hr'][i],
                'segment_ele_gain': intersections['segment_ele_gain'][i],
                'segment_ele_loss': intersections['segment_ele_loss'][i],
                'start_time': intersections['gate_times'][i][0],
                'gate_ordered': intersections['gate_ordered'][i],
                'lap_number': intersections['lap_number'][i],
                'gps_point_index_ordered': intersections['gps_point_index_ordered'][i],
                'sub_segment_times': intersections['sub_segment_times'][i],
                'sub_segment_distances': intersections['sub_segment_distances'][i],
                'sub_segment_paces': intersections['sub_segment_paces'][i],
                'gate_times': intersections['gate_times'][i]
                }
            segment_mappings.append(db_mapping)
#    core_logger.print_to_log(segment_mappings)
    return segment_mappings



def gps_trace_gate_intersections(gps_trace: streams_models.ActivityStreams, segment: segments_models.Segments, db: Session):
    # Takes a GPS Trace and checks that it passes through each gate

    # Returns null if the GPS trace does not pass through all gates
    # otherwise returns a sequence of intersections with each gate
    core_logger.print_to_log(f"Checking if activity stream {gps_trace.activity_id} passes through {segment.name.strip()}.")

    # Check for a valid GPS trace and segment
    if gps_trace is None or gps_trace.stream_waypoints is None or len(gps_trace.stream_waypoints) < 2:
        core_logger.print_to_log("Invalid GPS trace.")
        return None
    if segment is None or len(segment.gates) == 0:
        core_logger.print_to_log("No gates provided.")
        return None

    # Create a spatial tree of the GPS trace
    gps_points = [Point(pt['lat'], pt['lon']) for pt in gps_trace.stream_waypoints]

    # Retrieve other streams items that could be of interest
    activity_streams = streams_crud.get_activity_streams(gps_trace.activity_id, segment.user_id, db)

    hr_points = None
    ele_stream = None

    for stream in activity_streams:
        if stream.stream_type == 1:
            # Handle HR stream
            hr = [pt['hr'] for pt in stream.stream_waypoints]
            hr_points = hr[:-1] + [hr[-1]] * (len(gps_points) - len(hr))
        elif stream.stream_type == 4:
            # Handle Elevation stream
            ele_stream = stream
            ele = [pt['ele'] for pt in stream.stream_waypoints]

    segment_intersections = {}
    # Iterate through each gate in the segment
    for gate_index, gate in enumerate(segment.gates):
        gateline = LineString([gate[0], gate[1]])

        gps_point_index_intersections = []
        gps_point_intersections = []
        intersection_distance = []
        intersection_array = []

        found = False
        # Check if the GPS trace intersects with the gate line, including consecutive points to obtain all intersections
        for i in range(len(gps_points) - 1):
            seg = LineString([gps_points[i], gps_points[i+1]])
            if seg.intersects(gateline):
                intersection = seg.intersection(gateline)
                # Store intersection info as needed
                gps_point_index_intersections.append((i, i + 1))
                gps_point_intersections.append((gps_trace.stream_waypoints[i], gps_trace.stream_waypoints[i + 1]))
                intersection_distance.append([distance_between_points(gps_points[i], intersection), distance_between_points(gps_points[i + 1], intersection)])
                intersection_array.append(intersection)

                found = True
        if not found:
            core_logger.print_to_log(f"FAIL: GPS trace did not pass through gate {gate_index}.")
            return None   # Check if GPS trace passes through all the gates
        
        # Store the intersections for this gate
        segment_intersections[gate_index] = {
            'gate': gate,
            'gps_point_index_intersections': gps_point_index_intersections,
            'gps_point_intersections': gps_point_intersections,
            'intersection': intersection_array,
            'intersection_distance': intersection_distance
        }

    intersection_list = []
    for (gate_index, intersections) in segment_intersections.items():
        #core_logger.print_to_log(intersections)
        for i in range(len(intersections['gps_point_index_intersections'])):
            intersection_list.append((gate_index, 
                                      intersections['gps_point_index_intersections'][i],
                                      intersections['gps_point_intersections'][i], 
                                      intersections['intersection_distance'][i]))

    intersection_list_sorted = sorted(intersection_list, key=lambda x: x[1][0])
    #core_logger.print_to_log(intersection_list)
    #core_logger.print_to_log(intersection_list_sorted)

    gate_ordered = []
    gps_point_index_ordered = []
    gps_point_ordered = []
    intersection_distance_ordered = []
    last_gps_point_index = None
    for (gate_index, gps_point_index, gps_point, intersection_distance) in intersection_list_sorted:
        # Do not add the same GPS point index multiple times
        if gps_point_index[0] != last_gps_point_index:
            last_gps_point_index = gps_point_index[0]            

            gate_ordered.append(gate_index)
            gps_point_index_ordered.append(gps_point_index)
            gps_point_ordered.append(gps_point)
            intersection_distance_ordered.append(intersection_distance)
    #core_logger.print_to_log(gps_point_index_ordered)
    #core_logger.print_to_log("Prior to trimming:")
    #core_logger.print_to_log(gate_ordered)

    first_gate = 0
    last_gate = len(segment.gates) - 1

    # Trim the gate_ordered list to the first instance of the first gate and the last instance of the last gate
    for i in range(len(gate_ordered) -1):
        if gate_ordered[i] == first_gate and gate_ordered[i+1] != first_gate:
            first_gate = i
            break
    for i in range(len(gate_ordered) - 1, -1, -1):
        if gate_ordered[i] == last_gate and gate_ordered[i-1] != last_gate:
            last_gate = i
            break
    gate_ordered = gate_ordered[first_gate:last_gate + 1]
    gps_point_index_ordered = gps_point_index_ordered[first_gate:last_gate + 1]
    gps_point_ordered = gps_point_ordered[first_gate:last_gate + 1]
    intersection_distance_ordered = intersection_distance_ordered[first_gate:last_gate + 1]

    # Gates don't need to be passed in sequential order, but they must be passed through in order across the entire trace
    # Check that gates are passed through in order
    current_gate_index = 0
    for i in range(len(gate_ordered)):
        if gate_ordered[i] == current_gate_index:
            current_gate_index += 1
            #core_logger.print_to_log(current_gate_index)
        if current_gate_index > len(segment.gates) - 1:
            break
    if current_gate_index <= len(segment.gates) - 1:
        core_logger.print_to_log("FAIL: GPS trace does not pass through gates in order.")
        return None

    # core_logger.print_to_log("GPS trace passes through gates in the following order:")
    # core_logger.print_to_log(gate_ordered)
    core_logger.print_to_log("SUCCESS: GPS trace from activity {0} passes through {1}.".format(gps_trace.activity_id, segment.name.strip()))

    mode = 'linear' # or 'laps'

    # Check for repeating patterns in the gates
    laps = find_repeating_pattern_valid(gate_ordered)
    first_gate = 0
    last_gate = len(segment.gates) - 1
    if laps is not None:
        # Trim laps to the first instance of the first gate and the last instance of the last gate
        for i in range(len(laps)):
            if laps[i] == first_gate and laps[i+1] != first_gate:
                first_gate = i
                break
        for i in range(len(laps) - 1, -1, -1):
            if laps[i] == last_gate and laps[i-1] != last_gate:
                last_gate = i
                break
        laps = laps[first_gate:last_gate + 1]
        if len(laps) > 1:
            mode = 'laps'
            # core_logger.print_to_log(f"Found repeating pattern in gates: {laps}.")

    # Calculate the time for each gate and segment
    gate_times = []
    segment_times = []
    segment_distance = []
    segment_paces = []
    segment_avg_hr = []
    segment_max_hr = []
    segment_ele_gain = []
    segment_ele_loss = []
    sub_segment_times = []
    sub_segment_distances = []
    sub_segment_paces = []
    if mode == 'linear':
        # Look forward and find first gate and identify full gate sequence to first instance of last gate
        # (can't do this previously, as it removes laps)
        first_gate_idx = None
        last_gate_idx = None
        curr_gate = first_gate
        for i in range(len(gate_ordered)-1):
            if gate_ordered[i] == curr_gate:
                if curr_gate == first_gate:
                    first_gate_idx = i
                elif curr_gate == last_gate:
                    last_gate_idx = i
                curr_gate += 1

        if (first_gate_idx and last_gate_idx):
            gate_ordered = gate_ordered[first_gate_idx:last_gate_idx + 1]
            gps_point_index_ordered = gps_point_index_ordered[first_gate_idx:last_gate_idx + 1]
            gps_point_ordered = gps_point_ordered[first_gate_idx:last_gate_idx + 1]
            intersection_distance_ordered = intersection_distance_ordered[first_gate_idx:last_gate_idx + 1]

        # Validate segment in reverse (can't do this previously as it removes laps)
        # Look for the last instance of the last gate, and the last instance of first gate
        first_gate_idx = None
        last_gate_idx = None
        for i in range(len(gate_ordered)-1, -1, -1):
            if gate_ordered[i] == last_gate:
                if not last_gate_idx:
                    last_gate_idx = i
            if gate_ordered[i] == first_gate:
                if not first_gate_idx:
                    first_gate_idx = i

        if (first_gate_idx and last_gate_idx):
            gate_ordered = gate_ordered[first_gate_idx:last_gate_idx + 1]
            gps_point_index_ordered = gps_point_index_ordered[first_gate_idx:last_gate_idx + 1]
            gps_point_ordered = gps_point_ordered[first_gate_idx:last_gate_idx + 1]
            intersection_distance_ordered = intersection_distance_ordered[first_gate_idx:last_gate_idx + 1]

        sub_segment_time = []
        sub_segment_distance = []
        sub_segment_pace = []
        gate_datetime = []
        lap_number = [1]
        first_gate_time = None
        first_point_index = None
        last_point_index = None
        for i in range(len(gps_point_index_ordered)):
            # Get the time of the first GPS point in the pair
            gps_point_1 = gps_trace.stream_waypoints[gps_point_index_ordered[i][0]]
            gps_point_2 = gps_trace.stream_waypoints[gps_point_index_ordered[i][1]]
            gate_time_1 = datetime.fromisoformat(gps_point_1['time'])
            gate_time_2 = datetime.fromisoformat(gps_point_2['time'])
            delta_time = gate_time_2 - gate_time_1
            gate_time = gate_time_1 + delta_time * intersection_distance_ordered[i][0] / (intersection_distance_ordered[i][0] + intersection_distance_ordered[i][1])
            gate_datetime.append(gate_time.isoformat())
            if first_gate_time is None:
                first_gate_time = gate_time
                first_point_index = gps_point_index_ordered[i][1]
            else:
                sub_segment_time.append((gate_time - first_gate_time).total_seconds())

                sub_segment_points = gps_points[gps_point_index_ordered[i-1][1]:gps_point_index_ordered[i][0]]
                distance = calculate_distance(sub_segment_points)
                sub_segment_distance.append(distance)
                sub_segment_pace.append(activity_utils.calculate_pace(distance, first_gate_time, gate_time))
                last_point_index = gps_point_index_ordered[i][0]
        segment_time = ((datetime.fromisoformat(gate_datetime[-1]) - datetime.fromisoformat(gate_datetime[0])).total_seconds())
        distance = sum(sub_segment_distance)
        segment_pace = activity_utils.calculate_pace(distance, datetime.fromisoformat(gate_datetime[0]), datetime.fromisoformat(gate_datetime[-1]))
        if hr_points:
            segment_hr_points = hr_points[first_point_index:last_point_index]
            segment_avg_hr.append(statistics.mean(segment_hr_points))
            segment_max_hr.append(max(segment_hr_points))
        if ele_stream:
            segment_ele_waypoints = ele_stream.stream_waypoints[first_point_index:last_point_index]
            ele_gain, ele_loss = activity_utils.compute_elevation_gain_and_loss(segment_ele_waypoints)
            segment_ele_gain.append(ele_gain)
            segment_ele_loss.append(ele_loss)
        segment_times.append(segment_time)
        segment_paces.append(segment_pace)
        sub_segment_times.append(sub_segment_time)
        sub_segment_distances.append(sub_segment_distance)
        sub_segment_paces.append(sub_segment_pace)
        segment_distance.append(distance)
        gate_times.append(gate_datetime)

        gate_ordered = [gate_ordered]
        gps_point_index_ordered = [gps_point_index_ordered]

        # core_logger.print_to_log(f"Total time for segment {segment.name.strip()} is {segment_time}.")
    if mode == 'laps':
        # Calculate the time for each lap
        lap_count = 1
        laps_gate_ordered = []
        laps_gps_point_index_ordered = []
        lap_number = []
        for i in range(len(gps_point_index_ordered)-len(laps)+1):
            if gate_ordered[i:i+len(laps)] == laps:
                # This is a lap
                # core_logger.print_to_log(f"Lap {lap_count} completed.")
                sub_segment_time = []
                sub_segment_distance = []
                sub_segment_pace = []
                first_gate_time = None
                new_gate_ordered = []
                new_gps_point_index_ordered = []
                gate_datetime = []
                first_point_index = None
                last_point_index = None
                for j in range(len(laps)):
                    new_gate_ordered.append(laps[j])
                    new_gps_point_index_ordered.append(gps_point_index_ordered[i+j])
                    gps_point_1 = gps_trace.stream_waypoints[gps_point_index_ordered[i+j][0]]
                    gps_point_2 = gps_trace.stream_waypoints[gps_point_index_ordered[i+j][1]]
                    gate_time_1 = datetime.fromisoformat(gps_point_1['time'])
                    gate_time_2 = datetime.fromisoformat(gps_point_2['time'])
                    delta_time = gate_time_2 - gate_time_1
                    gate_time = gate_time_1 + delta_time * intersection_distance_ordered[i+j][0] / (intersection_distance_ordered[i+j][0] + intersection_distance_ordered[i+j][1])
                    gate_datetime.append(gate_time.isoformat())
                    if first_gate_time is None:
                        first_gate_time = gate_time
                        first_point_index = gps_point_index_ordered[i+j][1]
                    else:
                        sub_segment_time.append((gate_time - first_gate_time).total_seconds())

                        sub_segment_points = gps_points[gps_point_index_ordered[i+j-1][1]:gps_point_index_ordered[i+j][0]]
                        distance = calculate_distance(sub_segment_points)
                        sub_segment_distance.append(distance)
                        sub_segment_pace.append(activity_utils.calculate_pace(distance, first_gate_time, gate_time))
                        last_point_index = gps_point_index_ordered[i+j][0]
                segment_time = (datetime.fromisoformat(gate_datetime[-1]) - datetime.fromisoformat(gate_datetime[0])).total_seconds()
                distance = sum(sub_segment_distance)
                segment_pace = activity_utils.calculate_pace(distance, datetime.fromisoformat(gate_datetime[0]), datetime.fromisoformat(gate_datetime[-1]))
                if hr_points:
                    segment_hr_points = hr_points[first_point_index:last_point_index]
                    segment_avg_hr.append(statistics.mean(segment_hr_points))
                    segment_max_hr.append(max(segment_hr_points))
                if ele_stream:
                    segment_ele_waypoints = ele_stream.stream_waypoints[first_point_index:last_point_index]
                    ele_gain, ele_loss = activity_utils.compute_elevation_gain_and_loss(segment_ele_waypoints)
                    segment_ele_gain.append(ele_gain)
                    segment_ele_loss.append(ele_loss)
                segment_times.append(segment_time)
                sub_segment_times.append(sub_segment_time)
                sub_segment_distances.append(sub_segment_distance)
                sub_segment_paces.append(sub_segment_pace)
                segment_distance.append(distance)
                segment_paces.append(segment_pace)
                laps_gate_ordered.append(new_gate_ordered)
                laps_gps_point_index_ordered.append(new_gps_point_index_ordered)
                lap_number.append(lap_count)
                gate_times.append(gate_datetime)
                lap_count += 1
        gate_ordered = laps_gate_ordered
        gps_point_index_ordered = laps_gps_point_index_ordered

    result = {
        'segment_name': segment.name.strip(),
        'gate_ordered': gate_ordered,
        'lap_number': lap_number,
        'gps_point_index_ordered': gps_point_index_ordered,
        'sub_segment_times': sub_segment_times if len(sub_segment_times) > 0 else None,
        'sub_segment_distances': sub_segment_distances if len(sub_segment_distances) > 0 else None,
        'sub_segment_paces': sub_segment_paces if len(sub_segment_paces) > 0 else None,
        'segment_times': segment_times if len(segment_times) > 0 else None,
        'segment_distance': segment_distance if len(segment_distance) > 0 else None,
        'segment_pace': segment_paces if len(segment_paces) > 0 else None,
        'segment_avg_hr': segment_avg_hr if len(segment_avg_hr) > 0 else None,
        'segment_max_hr': segment_max_hr if len(segment_max_hr) > 0 else None,
        'segment_ele_gain': segment_ele_gain if len(segment_ele_gain) > 0 else None,
        'segment_ele_loss': segment_ele_loss if len(segment_ele_loss) > 0 else None,
        'gate_times': gate_times if len(gate_times) > 0 else None,
    }

    return result

def transform_model_segment_to_schema_segment(
        segment: segments_models.Segments
) -> segments_schema.Segments:
    
    # Create a new segment object
    new_segment = segments_schema.Segments(
        id=segment.id,
        user_id=segment.user_id,
        name=segment.name.strip(),
        activity_type=segment.activity_type,
        gates=segment.gates,
        city=segment.city,
        town=segment.town,
        country=segment.country,
    )

    return new_segment

def transform_schema_segment_to_model_segment(
    segment: segments_schema.Segments,
    user_id: int,
) -> segments_models.Segments:
    
    # Create a new segment object
    new_segment = segments_models.Segments(
        name=segment.name,
        user_id=user_id,
        activity_type=segment.activity_type,
        gates=segment.gates,
        town=segment.town,
        city=segment.city,
        country=segment.country
    )

    return new_segment
