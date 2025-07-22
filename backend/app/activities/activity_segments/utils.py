import activities.activity_segments.schema as segments_schema
import activities.activity_segments.models as segments_models
import activities.activity_streams.models as streams_models
from shapely.geometry import Point, LineString, MultiPoint
from datetime import datetime
import core.logger as core_logger

def distance_between_points(point1: Point, point2: Point) -> float:
    # Returns the distance between two points.
    return ((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2) ** 0.5

def find_repeating_pattern(lst):
    n = len(lst)
    for size in range(1, n // 2 + 1):
        pattern = lst[:size]
        # Build what the list would look like if the pattern repeated
        repeated = (pattern * (n // size + 1))[:n]
        if repeated == lst:
            return pattern
        # If not a perfect repeat, check for partial repeats
        # Find all occurrences of the pattern in the list
        matches = True
        for i in range(0, n, size):
            if lst[i:i+size] != pattern[:min(size, n-i)]:
                matches = False
                break
        if matches:
            return pattern
    return None

def gps_trace_gate_intersections(gps_trace: streams_models.ActivityStreams, segment: segments_models.Segment):
    # Takes a GPS Trace and checks that it passes through each gate

    # Returns null if the GPS trace does not pass through all gates
    # otherwise returns a sequence of intersections with each gate

    # Check for a valid GPS trace and segment
    if gps_trace is None or gps_trace.stream_waypoints is None or len(gps_trace.stream_waypoints) < 2:
        core_logger.print_to_log("Invalid GPS trace.")
        return None
    if segment is None or len(segment.gates) == 0:
        core_logger.print_to_log("No gates provided.")
        return None

    # Create a spatial tree of the GPS trace
    #gps_points = []
    #for point in gps_trace.stream_waypoints:
    #    gps_points.append(Point(point['lat'], point['lon']))
    gps_points = [Point(pt['lat'], pt['lon']) for pt in gps_trace.stream_waypoints]
    core_logger.print_to_log(f"Checking if activity stream {gps_trace.activity_id} passes through {segment.name.strip()}.")

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
    for i in range(len(gate_ordered)):
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

    core_logger.print_to_log("GPS trace passes through gates in the following order:")
    core_logger.print_to_log(gate_ordered)
    core_logger.print_to_log("SUCCESS: GPS trace from activity {0} passes through {1}.".format(gps_trace.activity_id, segment.name.strip()))

    mode = 'linear' # or 'laps'

    # Check for repeating patterns in the gates
    laps = find_repeating_pattern(gate_ordered)
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
            core_logger.print_to_log(f"Found repeating pattern in gates: {laps}.")

    # Calculate the time for each gate and segment
    gate_times = []
    segment_times = []
    sub_segment_times = []
    if mode == 'linear':
        times = []
        sub_segment_time = []
        first_gate_time = None
        for i in range(len(gps_point_index_ordered)):
            # Get the time of the first GPS point in the pair
            gps_point_1 = gps_trace.stream_waypoints[gps_point_index_ordered[i][0]]
            gps_point_2 = gps_trace.stream_waypoints[gps_point_index_ordered[i][1]]
            gate_time_1 = datetime.fromisoformat(gps_point_1['time'])
            gate_time_2 = datetime.fromisoformat(gps_point_2['time'])
            delta_time = gate_time_2 - gate_time_1
            gate_time = gate_time_1 + delta_time * intersection_distance_ordered[i][0] / (intersection_distance_ordered[i][0] + intersection_distance_ordered[i][1])
            if first_gate_time is None:
                first_gate_time = gate_time
            else:
                sub_segment_time.append((gate_ordered[i], (gate_time - first_gate_time).total_seconds()))
            core_logger.print_to_log(f"Gate {gate_ordered[i]} passed at {gate_time.isoformat()}")
            times.append((gate_ordered[i], gate_time.isoformat()))
        segment_time = ((datetime.fromisoformat(times[len(times)-1][1]) - datetime.fromisoformat(times[0][1])).total_seconds())
        gate_times.append(times)
        segment_times.append(segment_time)
        sub_segment_times.append(sub_segment_time)
        core_logger.print_to_log(f"Total time for segment {segment.name.strip()} is {segment_time}.")
    if mode == 'laps':
        # Calculate the time for each lap
        lap_number = 1
        for i in range(len(gps_point_index_ordered)-len(laps)+1):
            if gate_ordered[i:i+len(laps)] == laps:
                # This is a lap
                core_logger.print_to_log(f"Lap {lap_number} completed.")
                lap_times = []
                sub_segment_time = []
                first_gate_time = None
                for j in range(len(laps)):
                    gps_point_1 = gps_trace.stream_waypoints[gps_point_index_ordered[i+j][0]]
                    gps_point_2 = gps_trace.stream_waypoints[gps_point_index_ordered[i+j][1]]
                    gate_time_1 = datetime.fromisoformat(gps_point_1['time'])
                    gate_time_2 = datetime.fromisoformat(gps_point_2['time'])
                    delta_time = gate_time_2 - gate_time_1
                    gate_time = gate_time_1 + delta_time * intersection_distance_ordered[i+j][0] / (intersection_distance_ordered[i+j][0] + intersection_distance_ordered[i+j][1])
                    if first_gate_time is None:
                        first_gate_time = gate_time
                    else:
                        sub_segment_time.append((gate_ordered[i+j], (gate_time - first_gate_time).total_seconds()))
                    core_logger.print_to_log(f"Gate {gate_ordered[i+j]} passed at {gate_time.isoformat()}")
                    lap_times.append((gate_ordered[i+j], gate_time.isoformat()))
                gate_times.append(lap_times)
                segment_time = ((datetime.fromisoformat(lap_times[len(lap_times)-1][1]) - datetime.fromisoformat(lap_times[0][1])).total_seconds())
                core_logger.print_to_log(f"Total time for lap {lap_number} of segment {segment.name.strip()} is {segment_time}.")
                # Append the segment time to the list
                segment_times.append(segment_time)
                sub_segment_times.append(sub_segment_time)
                lap_number += 1

    result = {
        'segment_name': segment.name.strip(),
        'gate_ordered': gate_ordered,
        'gps_point_index_ordered': gps_point_index_ordered,
        'sub_segment_times': sub_segment_times if len(sub_segment_times) > 0 else None,
        'segment_times': segment_times if len(segment_times) > 0 else None,
        'gate_times': gate_times if len(gate_times) > 0 else None,
    }

    return result

def transform_schema_segment_to_model_segment(
    segment: segments_schema.Segment,
    user_id: int,
) -> segments_models.Segment:
    
    # Create a new segment object
    new_segment = segments_models.Segment(
        name=segment.name,
        user_id=user_id,
        activity_type=segment.activity_type,
        gates=segment.gates,
    )

    return new_segment
    