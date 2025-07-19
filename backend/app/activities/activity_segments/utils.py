import activities.activity_segments.schema as segments_schema
import activities.activity_segments.utils as segments_utils
import activities.activity_segments.models as segments_models
import activities.activity_streams.models as streams_models
from shapely.geometry import Point, LineString, MultiPoint
from shapely.strtree import STRtree
import core.logger as core_logger

def split_consecutive_sequences(sequence: list) -> list:
    """
    Splits a list of consecutive integers into chunks.
    For example, [1, 2, 3, 5, 6] will be split into [[1, 2, 3], [5, 6]].
    """
    sequence = sorted(sequence)

    chunks = []
    current_chunk = [sequence[0]]

    for i in range(1, len(sequence)):
        if sequence[i] == sequence[i - 1] + 1:
            current_chunk.append(sequence[i])
        else:
            chunks.append(current_chunk)
            current_chunk = [sequence[i]]

    chunks.append(current_chunk)
    return chunks    

def distance_between_points(point1: Point, point2: Point) -> float:
    """
    Returns the distance between two points.
    """
    return ((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2) ** 0.5

def adjacent_points(points: list, intersection: Point) -> list:
    """
    Returns a list of points that are adjacent to the intersection point.
    """
    for i in range(len(points)-1):
        current_point = Point(points[i])
        next_point = Point(points[i + 1])
        min_distance = float('inf')

        # the distance between the intersection point and the current point
        distance = distance_between_points(current_point, intersection)

        # the distance between the intersection point and the next point
        distance_next = distance_between_points(next_point, intersection)

        # If the intersection point is to the left of the current point and to the right of the next point,
        # or if the intersection point is to the right of the current point and to the left of the next point,
        # update the minimum distance and the closest points
        if (intersection.x < current_point.x and intersection.x > next_point.x) or (intersection.x > current_point.x and intersection.x < next_point.x):
            if distance + distance_next < min_distance:
                min_distance = distance + distance_next
                closest_points = [current_point, next_point]
                intersection_distance = [distance_between_points(current_point, intersection), distance_between_points(next_point, intersection)]
                intersection_index = [i, i + 1]

    return intersection_index, closest_points, intersection_distance

def gps_trace_gate_intersections(gps_trace: streams_models.ActivityStreams, segment: segments_models.Segment):
    # Takes a GPS Trace and checks that it passes through each gate

    # Returns null if the GPS trace does not pass through all gates
    # otherwise returns a sequence of intersections with each gate

    # This is a check to ensure that the gps trace is not None
    if gps_trace is None:
        core_logger.print_to_log("GPS trace is None.")
        return None
    # Ensure gps trace is more than 1 point long
    if gps_trace.stream_waypoints is None or len(gps_trace.stream_waypoints) < 2:
        core_logger.print_to_log("GPS trace is too short to check gates.")
        return None
    # Ensure one or more gates
    if segment is None or len(segment.gates) == 0:
        core_logger.print_to_log("No gates provided.")
        return None

    # Create a spatial tree of the GPS trace
    gps_points = []
    for point in gps_trace.stream_waypoints:
        gps_points.append(Point(point['lat'], point['lon']))

    tree = STRtree(gps_points)

    core_logger.print_to_log("Checking if activity stream {0} passes through {1}.".format(gps_trace.activity_id, segment.name.strip()))
    # Check if GPS trace passes through all the gates

    segment_intersections = {}
    gate_index = 0
    for gate in segment.gates:
        # Check if the gate intersects with the GPS trace
        gps_point_index_intersections = []
        gps_point_intersections = []
        chunk_index_intersections = []
        chunk_line_intersections = []
        chunk_intersection_distance = []

        gateline = LineString([gate[0], gate[1]])

        potential_intersection = tree.query(gateline, predicate='dwithin', distance=0.0005)  # 0.0005 degrees is approximately 55 meters at the equator

        if len(potential_intersection) == 0:
            # GPS trace did not pass through the gate
            core_logger.print_to_log("FAIL: GPS trace did not pass through gate, due to no potential intersections detected.")
            return None

        # potential_intersection is a list of points that are within the bounding box of the gate line
        # We need to check if any of these points actually intersect with the gate line

        potential_intersection_chunks = split_consecutive_sequences(potential_intersection)

        chunk_passes = False
        for chunk in potential_intersection_chunks:
            # At least one chukk needs to pass through the gate line
            # Chunk needs to be at least 2 points long to form a line
            if len(chunk) > 2:
                # Convert chunk of points to a LineString
                chunk_line = LineString(gps_points[chunk[0]:chunk[-1] + 1])
                # Check if the chunk intersects with the gate line
                if chunk_line.intersects(gateline):
                    chunk_passes = True
                    intersection = chunk_line.intersection(gateline)
                    coords = chunk_line.coords

                    if type(intersection) == Point:
                        intersection_index, intersection_points, intersection_distance = adjacent_points(coords, intersection)

                        gps_point_index_intersections.append((chunk[0] + intersection_index[0], chunk[0] + intersection_index[1]))
                        gps_point_intersections.append((gps_trace.stream_waypoints[chunk[0] + intersection_index[0]], gps_trace.stream_waypoints[chunk[0] + intersection_index[1]]))
                        chunk_index_intersections.append(intersection_points)
                        chunk_line_intersections.append(intersection)
                        chunk_intersection_distance.append(intersection_distance)

                    if type(intersection) == MultiPoint:
                        for geom in intersection.geoms:
                            for point in geom.coords:
                                intersection_index, intersection_points, intersection_distance = adjacent_points(coords, Point(point))

                                gps_point_index_intersections.append((chunk[0] + intersection_index[0], chunk[0] + intersection_index[1]))
                                gps_point_intersections.append((gps_trace.stream_waypoints[chunk[0] + intersection_index[0]], gps_trace.stream_waypoints[chunk[0] + intersection_index[1]]))
                                chunk_index_intersections.append(intersection_points)
                                chunk_line_intersections.append(intersection)
                                chunk_intersection_distance.append(intersection_distance)

        if not chunk_passes:
            core_logger.print_to_log("FAIL: No chunk intercepted with the gate line. Therefore GPS trace did not pass through gate.")
            return None

        # If we reach here, the GPS trace passed through the gate
        segment_intersections[gate_index] = {
            'gate': gate,
            'gps_point_index_intersections': gps_point_index_intersections,
            'gps_point_intersections': gps_point_intersections,
            'chunk_index_intersections': chunk_index_intersections,
            'chunk_line_intersections': chunk_line_intersections,
            'chunk_intersection_distance': chunk_intersection_distance
        }

        gate_index += 1

    intersection_list = []
    for (gate_index, intersections) in segment_intersections.items():
        #core_logger.print_to_log(intersections)
        for i in range(len(intersections['gps_point_index_intersections'])):
            intersection_list.append((gate_index, 
                                      intersections['gps_point_index_intersections'][i], 
                                      intersections['gps_point_intersections'][i], 
                                      intersections['chunk_intersection_distance'][i]))

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
        if gate_ordered[i] == first_gate:
            first_gate = i
            break
    for i in range(len(gate_ordered) - 1, -1, -1):
        if gate_ordered[i] == last_gate:
            last_gate = i
            break
    gate_ordered = gate_ordered[first_gate:last_gate + 1]
    gps_point_index_ordered = gps_point_index_ordered[first_gate:last_gate + 1]
    gps_point_ordered = gps_point_ordered[first_gate:last_gate + 1]
    intersection_distance_ordered = intersection_distance_ordered[first_gate:last_gate + 1]

    # Gates don't need to be passed in sequential order, but they must be passed through in order across the entire trace
    # Check that gates are passed through in order

    #core_logger.print_to_log("After trimming:")
    #core_logger.print_to_log(gate_ordered)
    #core_logger.print_to_log("Last gate number: {0}".format(len(segment.gates) - 1))

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

    return (
        gate_ordered,
        gps_point_index_ordered,
        gps_point_ordered,
        intersection_distance_ordered
    )

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
    