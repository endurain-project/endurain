import activities.activity_segments.schema as segments_schema
import activities.activity_segments.utils as segments_utils
import activities.activity_segments.models as segments_models
import activities.activity_streams.models as streams_models
import shapely
from shapely.geometry import Point, LineString
from shapely.strtree import STRtree
import core.logger as core_logger

def gps_trace_pass_all_gates(gps_trace: streams_models.ActivityStreams, gates: segments_models.Segment):
    # Takes a GPS Trace and checks that it passes through each gate
    
    # TODO: add checks to ensure GPS trace passes through gates sequentially

    # TODO: Ensure gps trace is more than 1 point long

    # Create a spatial tree of the GPS trace
    gps_points = []
    for point in gps_trace.stream_waypoints:
        gps_points.append(Point(point['lat'], point['lon']))

    core_logger.print_to_log(gps_points[1].x)
    core_logger.print_to_log(gps_points[1].y)

    tree = STRtree(gps_points)

    # TODO: Ensure one or more gates

    # Check if GPS trace passes through all the gates
    for gate in gates.gates:
        # Check if the gate intersects with the GPS trace
        core_logger.print_to_log(gate)
        gateline = LineString([gate[0], gate[1]])
        intersection = []
        potential_intersection = tree.query(gateline)
        core_logger.print_to_log(potential_intersection)
#        for geom in potential_intersection:
#            if geom.intersects(gateline):
#                intersection.append(geom)
        if len(potential_intersection) == 0:
            # GPS trace did not pass through the gate
            return False
    return True

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
    