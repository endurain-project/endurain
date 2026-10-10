"""Version-pinned parser operations exposed only to data migrations."""

import modules.activities.activity_file_import.utils as file_import_utils
import modules.activities.activity_file_import.utils_fit_frames as fit_frames

generate_activity_laps = file_import_utils.generate_activity_laps
parse_frame_session = fit_frames.parse_frame_session
parse_frame_lap = fit_frames.parse_frame_lap
parse_frame_workout_step = fit_frames.parse_frame_workout_step
parse_frame_exercise_title = fit_frames.parse_frame_exercise_title
parse_frame_set = fit_frames.parse_frame_set
