CREATE TABLE public.account_security_generations (
    generation integer DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.account_security_generations.generation IS 'Counter advanced by every security change; a pending proof records the value it was created under';

COMMENT ON COLUMN public.account_security_generations.updated_at IS 'When the generation last changed';

COMMENT ON COLUMN public.account_security_generations.user_id IS 'User the generation belongs to';

CREATE TABLE public.activities (
    name character varying(250),
    description character varying(2500),
    distance integer NOT NULL,
    activity_type integer NOT NULL,
    start_time timestamp with time zone NOT NULL,
    end_time timestamp with time zone NOT NULL,
    city character varying(250),
    town character varying(250),
    country character varying(250),
    created_at timestamp with time zone NOT NULL,
    elevation_gain integer,
    elevation_loss integer,
    pace numeric(20,10),
    average_speed numeric(20,10),
    average_power integer,
    calories integer,
    visibility integer NOT NULL,
    strava_gear_id character varying(45),
    strava_activity_id bigint,
    total_elapsed_time numeric(20,10) NOT NULL,
    total_timer_time numeric(20,10) NOT NULL,
    max_speed numeric(20,10),
    max_power integer,
    normalized_power integer,
    average_hr integer,
    max_hr integer,
    average_cad integer,
    max_cad integer,
    workout_feeling integer,
    workout_rpe integer,
    garminconnect_activity_id bigint,
    garminconnect_gear_id character varying(45),
    timezone character varying(250),
    hide_start_time boolean NOT NULL,
    hide_location boolean NOT NULL,
    hide_map boolean NOT NULL,
    hide_hr boolean NOT NULL,
    hide_power boolean NOT NULL,
    hide_cadence boolean NOT NULL,
    hide_elevation boolean NOT NULL,
    hide_speed boolean NOT NULL,
    hide_pace boolean NOT NULL,
    hide_laps boolean NOT NULL,
    hide_workout_sets_steps boolean NOT NULL,
    hide_gear boolean NOT NULL,
    private_notes character varying(2500),
    is_hidden boolean NOT NULL,
    import_info json,
    tracker_manufacturer character varying(250),
    tracker_model character varying(250),
    map_thumbnail_path character varying(500),
    total_cycles integer,
    dedup_key character varying(255),
    version integer DEFAULT 1 NOT NULL,
    location_next_lookup_at timestamp with time zone,
    thumbnail_next_attempt_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    gear_id uuid,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.activities.name IS 'Activity name (May include spaces)';

COMMENT ON COLUMN public.activities.description IS 'Activity description (May include spaces)';

COMMENT ON COLUMN public.activities.distance IS 'Distance in meters';

COMMENT ON COLUMN public.activities.activity_type IS 'Gear type (1 - mountain bike, 2 - gravel bike, ...)';

COMMENT ON COLUMN public.activities.start_time IS 'Activity start date (DATETIME)';

COMMENT ON COLUMN public.activities.end_time IS 'Activity end date (DATETIME)';

COMMENT ON COLUMN public.activities.city IS 'Activity city (May include spaces)';

COMMENT ON COLUMN public.activities.town IS 'Activity town (May include spaces)';

COMMENT ON COLUMN public.activities.country IS 'Activity country (May include spaces)';

COMMENT ON COLUMN public.activities.created_at IS 'Activity creation date (DATETIME)';

COMMENT ON COLUMN public.activities.elevation_gain IS 'Elevation gain in meters';

COMMENT ON COLUMN public.activities.elevation_loss IS 'Elevation loss in meters';

COMMENT ON COLUMN public.activities.pace IS 'Pace seconds per meter (s/m)';

COMMENT ON COLUMN public.activities.average_speed IS 'Average speed seconds per meter (s/m)';

COMMENT ON COLUMN public.activities.average_power IS 'Average power (watts)';

COMMENT ON COLUMN public.activities.calories IS 'The number of kilocalories consumed during this activity';

COMMENT ON COLUMN public.activities.visibility IS '0 - public, 1 - followers, 2 - private';

COMMENT ON COLUMN public.activities.strava_gear_id IS 'Strava gear ID';

COMMENT ON COLUMN public.activities.strava_activity_id IS 'Strava activity ID';

COMMENT ON COLUMN public.activities.total_elapsed_time IS 'Activity total elapsed time (s)';

COMMENT ON COLUMN public.activities.total_timer_time IS 'Activity total timer time (s)';

COMMENT ON COLUMN public.activities.max_speed IS 'Max speed seconds per meter (s/m)';

COMMENT ON COLUMN public.activities.max_power IS 'Max power (watts)';

COMMENT ON COLUMN public.activities.normalized_power IS 'Normalized power (watts)';

COMMENT ON COLUMN public.activities.average_hr IS 'Average heart rate (bpm)';

COMMENT ON COLUMN public.activities.max_hr IS 'Max heart rate (bpm)';

COMMENT ON COLUMN public.activities.average_cad IS 'Average cadence (rpm)';

COMMENT ON COLUMN public.activities.max_cad IS 'Max cadence (rpm)';

COMMENT ON COLUMN public.activities.workout_feeling IS 'Workout feeling (0 to 100)';

COMMENT ON COLUMN public.activities.workout_rpe IS 'Workout RPE (10 to 100)';

COMMENT ON COLUMN public.activities.garminconnect_activity_id IS 'Garmin Connect activity ID';

COMMENT ON COLUMN public.activities.garminconnect_gear_id IS 'Garmin Connect gear ID';

COMMENT ON COLUMN public.activities.timezone IS 'Activity timezone (May include spaces)';

COMMENT ON COLUMN public.activities.hide_start_time IS 'Hide activity start time';

COMMENT ON COLUMN public.activities.hide_location IS 'Hide activity location';

COMMENT ON COLUMN public.activities.hide_map IS 'Hide activity map';

COMMENT ON COLUMN public.activities.hide_hr IS 'Hide activity heart rate';

COMMENT ON COLUMN public.activities.hide_power IS 'Hide activity power';

COMMENT ON COLUMN public.activities.hide_cadence IS 'Hide activity cadence';

COMMENT ON COLUMN public.activities.hide_elevation IS 'Hide activity elevation';

COMMENT ON COLUMN public.activities.hide_speed IS 'Hide activity speed';

COMMENT ON COLUMN public.activities.hide_pace IS 'Hide activity pace';

COMMENT ON COLUMN public.activities.hide_laps IS 'Hide activity laps';

COMMENT ON COLUMN public.activities.hide_workout_sets_steps IS 'Hide activity workout sets and steps';

COMMENT ON COLUMN public.activities.hide_gear IS 'Hide activity gear';

COMMENT ON COLUMN public.activities.private_notes IS 'Activity private notes (May include spaces)';

COMMENT ON COLUMN public.activities.is_hidden IS 'Indicates if the activity is hidden (e.g., duplicate activity waiting to be reviewed by the user)';

COMMENT ON COLUMN public.activities.tracker_manufacturer IS 'Tracker manufacturer (e.g., Garmin, Suunto, Polar)';

COMMENT ON COLUMN public.activities.tracker_model IS 'Tracker model (e.g., Forerunner 245, Ambit3 Peak, Vantage V2)';

COMMENT ON COLUMN public.activities.map_thumbnail_path IS 'Relative path to the pre-generated static map thumbnail image';

COMMENT ON COLUMN public.activities.total_cycles IS 'Total number of cycles (e.g., pedal strokes) recorded';

COMMENT ON COLUMN public.activities.dedup_key IS 'Stable idempotency key (provider id or content hash) to no-op re-imports';

COMMENT ON COLUMN public.activities.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.activities.location_next_lookup_at IS 'Earliest time the location backfill retries an activity with no resolved location';

COMMENT ON COLUMN public.activities.thumbnail_next_attempt_at IS 'Earliest time the thumbnail backfill retries an activity that has no thumbnail';

COMMENT ON COLUMN public.activities.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.activities.gear_id IS 'Gear ID associated with this activity';

COMMENT ON COLUMN public.activities.user_id IS 'User ID that the activity belongs';

CREATE TABLE public.activities_streams (
    stream_type integer NOT NULL,
    stream_waypoints json NOT NULL,
    strava_activity_stream_id integer,
    id uuid NOT NULL,
    activity_id uuid NOT NULL
);

COMMENT ON COLUMN public.activities_streams.stream_type IS 'Stream type (1-HR, 2-Power, 3-Cadence, 4-Elevation, 5-Velocity, 6-Pace, 7-lat/lon)';

COMMENT ON COLUMN public.activities_streams.stream_waypoints IS 'Store waypoints data';

COMMENT ON COLUMN public.activities_streams.strava_activity_stream_id IS 'Strava activity stream ID';

COMMENT ON COLUMN public.activities_streams.activity_id IS 'Activity ID that the activity stream belongs';

CREATE TABLE public.activity_deletions (
    record_id uuid NOT NULL,
    deleted_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.activity_deletions.record_id IS 'The id the deleted record had';

COMMENT ON COLUMN public.activity_deletions.deleted_at IS 'When the record was deleted';

COMMENT ON COLUMN public.activity_deletions.user_id IS 'Owner of the deleted record';

CREATE TABLE public.activity_exercise_titles (
    id integer NOT NULL,
    exercise_category integer NOT NULL,
    exercise_name integer NOT NULL,
    wkt_step_name character varying(250) NOT NULL
);

COMMENT ON COLUMN public.activity_exercise_titles.exercise_category IS 'Exercise category';

COMMENT ON COLUMN public.activity_exercise_titles.exercise_name IS 'Exercise name ID';

COMMENT ON COLUMN public.activity_exercise_titles.wkt_step_name IS 'WKT step name (may include spaces)';

CREATE SEQUENCE public.activity_exercise_titles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.activity_exercise_titles_id_seq OWNED BY public.activity_exercise_titles.id;

CREATE TABLE public.activity_ingestion_jobs (
    id uuid CONSTRAINT activity_upload_jobs_id_not_null NOT NULL,
    filename character varying(255),
    staged_key character varying(500),
    status character varying(20) DEFAULT 'pending'::character varying CONSTRAINT activity_upload_jobs_status_not_null NOT NULL,
    error_code character varying(50),
    activity_ids jsonb,
    created_at timestamp with time zone DEFAULT now() CONSTRAINT activity_upload_jobs_created_at_not_null NOT NULL,
    updated_at timestamp with time zone DEFAULT now() CONSTRAINT activity_upload_jobs_updated_at_not_null NOT NULL,
    completed_at timestamp with time zone,
    kind character varying(20) DEFAULT 'upload'::character varying NOT NULL,
    idempotency_key character varying(255),
    request_fingerprint character varying(64),
    provider character varying(50),
    window_start timestamp with time zone,
    window_end timestamp with time zone,
    import_source character varying(50),
    files_total integer,
    files_done integer,
    files_failed integer,
    cursor character varying(500),
    retry_after timestamp with time zone,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.activity_ingestion_jobs.id IS 'Ingestion job identifier (UUIDv4)';

COMMENT ON COLUMN public.activity_ingestion_jobs.filename IS 'Original client filename for an upload, for display only';

COMMENT ON COLUMN public.activity_ingestion_jobs.staged_key IS 'Storage key of the staged upload; cleared once consumed';

COMMENT ON COLUMN public.activity_ingestion_jobs.status IS 'pending | processing | deferred | completed | failed';

COMMENT ON COLUMN public.activity_ingestion_jobs.error_code IS 'Sanitized failure reason when status is failed';

COMMENT ON COLUMN public.activity_ingestion_jobs.activity_ids IS 'Ids of the activities the import created';

COMMENT ON COLUMN public.activity_ingestion_jobs.created_at IS 'When the request was accepted';

COMMENT ON COLUMN public.activity_ingestion_jobs.updated_at IS 'When the job last changed state';

COMMENT ON COLUMN public.activity_ingestion_jobs.completed_at IS 'When the job reached a terminal state (completed/failed)';

COMMENT ON COLUMN public.activity_ingestion_jobs.kind IS 'upload | refresh | bulk_import';

COMMENT ON COLUMN public.activity_ingestion_jobs.idempotency_key IS 'Client-supplied Idempotency-Key for an upload; unique per user and kind';

COMMENT ON COLUMN public.activity_ingestion_jobs.request_fingerprint IS 'SHA-256 of the bytes the idempotency key was first used with';

COMMENT ON COLUMN public.activity_ingestion_jobs.provider IS 'Provider a refresh syncs; null syncs every linked provider';

COMMENT ON COLUMN public.activity_ingestion_jobs.window_start IS 'Start of the window a refresh fetches; null means the default window';

COMMENT ON COLUMN public.activity_ingestion_jobs.window_end IS 'End of the window a refresh fetches';

COMMENT ON COLUMN public.activity_ingestion_jobs.import_source IS 'Archive format a bulk import reads (generic or a provider export)';

COMMENT ON COLUMN public.activity_ingestion_jobs.files_total IS 'Importable files in a bulk import''s archive';

COMMENT ON COLUMN public.activity_ingestion_jobs.files_done IS 'Files a bulk import has imported so far';

COMMENT ON COLUMN public.activity_ingestion_jobs.files_failed IS 'Files a bulk import could not import';

COMMENT ON COLUMN public.activity_ingestion_jobs.cursor IS 'Last archive member a bulk import handled; the next batch resumes after it';

COMMENT ON COLUMN public.activity_ingestion_jobs.retry_after IS 'When a deferred refresh runs again; a provider''s rate limit clears then';

COMMENT ON COLUMN public.activity_ingestion_jobs.user_id IS 'User that owns the ingestion request';

CREATE TABLE public.activity_laps (
    start_time timestamp with time zone NOT NULL,
    start_position_lat numeric(20,10),
    start_position_long numeric(20,10),
    end_position_lat numeric(20,10),
    end_position_long numeric(20,10),
    total_elapsed_time numeric(20,10),
    total_timer_time numeric(20,10),
    total_distance numeric(20,10),
    total_cycles integer,
    total_calories integer,
    avg_heart_rate integer,
    max_heart_rate integer,
    avg_cadence integer,
    max_cadence integer,
    avg_power integer,
    max_power integer,
    total_ascent integer,
    total_descent integer,
    intensity character varying(250),
    lap_trigger character varying(250),
    sport character varying(250),
    sub_sport character varying(250),
    normalized_power integer,
    total_work integer,
    avg_vertical_oscillation numeric(20,10),
    avg_stance_time numeric(20,10),
    avg_fractional_cadence numeric(20,10),
    max_fractional_cadence numeric(20,10),
    enhanced_avg_pace numeric(20,10),
    enhanced_avg_speed numeric(20,10),
    enhanced_max_pace numeric(20,10),
    enhanced_max_speed numeric(20,10),
    enhanced_min_altitude numeric(20,10),
    enhanced_max_altitude numeric(20,10),
    avg_vertical_ratio numeric(20,10),
    avg_step_length numeric(20,10),
    id uuid NOT NULL,
    activity_id uuid NOT NULL
);

COMMENT ON COLUMN public.activity_laps.start_time IS 'Lap start date (DATETIME)';

COMMENT ON COLUMN public.activity_laps.start_position_lat IS 'Lap start position latitude';

COMMENT ON COLUMN public.activity_laps.start_position_long IS 'Lap start position longitude';

COMMENT ON COLUMN public.activity_laps.end_position_lat IS 'Lap end position latitude';

COMMENT ON COLUMN public.activity_laps.end_position_long IS 'Lap end position longitude';

COMMENT ON COLUMN public.activity_laps.total_elapsed_time IS 'Lap total elapsed time (s)';

COMMENT ON COLUMN public.activity_laps.total_timer_time IS 'Lap total timer time (s)';

COMMENT ON COLUMN public.activity_laps.total_distance IS 'Lap total distance (m)';

COMMENT ON COLUMN public.activity_laps.total_cycles IS 'Lap total cycles';

COMMENT ON COLUMN public.activity_laps.total_calories IS 'Lap total calories';

COMMENT ON COLUMN public.activity_laps.avg_heart_rate IS 'Lap average heart rate';

COMMENT ON COLUMN public.activity_laps.max_heart_rate IS 'Lap maximum heart rate';

COMMENT ON COLUMN public.activity_laps.avg_cadence IS 'Lap average cadence';

COMMENT ON COLUMN public.activity_laps.max_cadence IS 'Lap maximum cadence';

COMMENT ON COLUMN public.activity_laps.avg_power IS 'Lap average power';

COMMENT ON COLUMN public.activity_laps.max_power IS 'Lap maximum power';

COMMENT ON COLUMN public.activity_laps.total_ascent IS 'Lap total ascent (m)';

COMMENT ON COLUMN public.activity_laps.total_descent IS 'Lap total descent (m)';

COMMENT ON COLUMN public.activity_laps.intensity IS 'Lap intensity';

COMMENT ON COLUMN public.activity_laps.lap_trigger IS 'Lap trigger';

COMMENT ON COLUMN public.activity_laps.sport IS 'Lap sport';

COMMENT ON COLUMN public.activity_laps.sub_sport IS 'Lap sub sport';

COMMENT ON COLUMN public.activity_laps.normalized_power IS 'Lap normalized power';

COMMENT ON COLUMN public.activity_laps.total_work IS 'Lap total work';

COMMENT ON COLUMN public.activity_laps.avg_vertical_oscillation IS 'Lap average vertical oscillation';

COMMENT ON COLUMN public.activity_laps.avg_stance_time IS 'Lap average stance time';

COMMENT ON COLUMN public.activity_laps.avg_fractional_cadence IS 'Lap average fractional cadence';

COMMENT ON COLUMN public.activity_laps.max_fractional_cadence IS 'Lap maximum fractional cadence';

COMMENT ON COLUMN public.activity_laps.enhanced_avg_pace IS 'Lap enhanced average pace';

COMMENT ON COLUMN public.activity_laps.enhanced_avg_speed IS 'Lap enhanced average speed';

COMMENT ON COLUMN public.activity_laps.enhanced_max_pace IS 'Lap enhanced maximum pace';

COMMENT ON COLUMN public.activity_laps.enhanced_max_speed IS 'Lap enhanced maximum speed';

COMMENT ON COLUMN public.activity_laps.enhanced_min_altitude IS 'Lap enhanced minimum altitude';

COMMENT ON COLUMN public.activity_laps.enhanced_max_altitude IS 'Lap enhanced maximum altitude';

COMMENT ON COLUMN public.activity_laps.avg_vertical_ratio IS 'Lap average vertical ratio';

COMMENT ON COLUMN public.activity_laps.avg_step_length IS 'Lap average step length';

COMMENT ON COLUMN public.activity_laps.activity_id IS 'Activity ID that the activity lap belongs';

CREATE TABLE public.activity_media (
    media_path character varying(250),
    media_type integer NOT NULL,
    content_hash character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    activity_id uuid NOT NULL
);

COMMENT ON COLUMN public.activity_media.media_path IS 'Media path';

COMMENT ON COLUMN public.activity_media.media_type IS 'Media type (1 - photo)';

COMMENT ON COLUMN public.activity_media.content_hash IS 'SHA-256 of the media bytes, used to no-op re-imports of the same photo';

COMMENT ON COLUMN public.activity_media.created_at IS 'When the media record was created';

COMMENT ON COLUMN public.activity_media.activity_id IS 'Activity ID that the activity media belongs';

CREATE TABLE public.activity_sets (
    duration numeric(20,10) NOT NULL,
    repetitions integer,
    weight numeric(20,10),
    set_type character varying(250) NOT NULL,
    start_time timestamp with time zone NOT NULL,
    category integer,
    category_subtype integer,
    id uuid NOT NULL,
    activity_id uuid NOT NULL
);

COMMENT ON COLUMN public.activity_sets.duration IS 'Workout set duration';

COMMENT ON COLUMN public.activity_sets.repetitions IS 'Repetitions number';

COMMENT ON COLUMN public.activity_sets.weight IS 'Workout set exercise weight';

COMMENT ON COLUMN public.activity_sets.set_type IS 'Workout set type';

COMMENT ON COLUMN public.activity_sets.start_time IS 'Workout set start date';

COMMENT ON COLUMN public.activity_sets.category IS 'Category name';

COMMENT ON COLUMN public.activity_sets.category_subtype IS 'Category sub type number';

COMMENT ON COLUMN public.activity_sets.activity_id IS 'Activity ID that the activity lap belongs';

CREATE TABLE public.activity_workout_steps (
    message_index integer NOT NULL,
    duration_type character varying(250) NOT NULL,
    duration_value numeric(20,10),
    target_type character varying(250),
    target_value integer,
    intensity character varying(250),
    notes character varying(250),
    exercise_category integer,
    exercise_name integer,
    exercise_weight numeric(20,10),
    weight_display_unit character varying(250),
    secondary_target_value character varying(250),
    id uuid NOT NULL,
    activity_id uuid NOT NULL
);

COMMENT ON COLUMN public.activity_workout_steps.message_index IS 'Workout step message index';

COMMENT ON COLUMN public.activity_workout_steps.duration_type IS 'Workout step duration type';

COMMENT ON COLUMN public.activity_workout_steps.duration_value IS 'Workout step duration value';

COMMENT ON COLUMN public.activity_workout_steps.target_type IS 'Workout step target type';

COMMENT ON COLUMN public.activity_workout_steps.target_value IS 'Workout step target value';

COMMENT ON COLUMN public.activity_workout_steps.intensity IS 'Workout step intensity type';

COMMENT ON COLUMN public.activity_workout_steps.notes IS 'Workout step notes';

COMMENT ON COLUMN public.activity_workout_steps.exercise_category IS 'Workout step exercise category';

COMMENT ON COLUMN public.activity_workout_steps.exercise_name IS 'Exercise name ID';

COMMENT ON COLUMN public.activity_workout_steps.exercise_weight IS 'Workout step exercise weight';

COMMENT ON COLUMN public.activity_workout_steps.weight_display_unit IS 'Workout step weight display unit';

COMMENT ON COLUMN public.activity_workout_steps.secondary_target_value IS 'Workout step secondary target value';

COMMENT ON COLUMN public.activity_workout_steps.activity_id IS 'Activity ID that the activity workout steps belongs';

CREATE TABLE public.auth_known_devices (
    device_hash character varying(64) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    last_seen_at timestamp with time zone NOT NULL,
    security_generation integer NOT NULL,
    browser character varying(45),
    operating_system character varying(45),
    device_type character varying(45),
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.auth_known_devices.device_hash IS 'SHA-256 hex digest of the device id held in the browser''s cookie';

COMMENT ON COLUMN public.auth_known_devices.created_at IS 'First sign-in from the device';

COMMENT ON COLUMN public.auth_known_devices.last_seen_at IS 'Last sign-in from the device; the row is pruned 400 days after it';

COMMENT ON COLUMN public.auth_known_devices.security_generation IS 'Account security generation the device was registered under; stale once a security change follows';

COMMENT ON COLUMN public.auth_known_devices.browser IS 'Browser of the last sign-in from the device';

COMMENT ON COLUMN public.auth_known_devices.operating_system IS 'Operating system of the last sign-in from the device';

COMMENT ON COLUMN public.auth_known_devices.device_type IS 'Device type of the last sign-in from the device';

COMMENT ON COLUMN public.auth_known_devices.user_id IS 'User who signed in from the device';

CREATE TABLE public.follow_request_declines (
    declined_at timestamp with time zone NOT NULL,
    id uuid NOT NULL,
    follower_id uuid NOT NULL,
    followee_id uuid NOT NULL
);

COMMENT ON COLUMN public.follow_request_declines.declined_at IS 'When the request was declined';

COMMENT ON COLUMN public.follow_request_declines.follower_id IS 'ID of the requester whose request was declined';

COMMENT ON COLUMN public.follow_request_declines.followee_id IS 'ID of the user who declined the request';

CREATE TABLE public.follower_blocks (
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    blocker_id uuid NOT NULL,
    blocked_id uuid NOT NULL,
    CONSTRAINT ck_follower_blocks_not_self CHECK ((blocker_id <> blocked_id))
);

COMMENT ON COLUMN public.follower_blocks.blocker_id IS 'ID of the user who blocked';

COMMENT ON COLUMN public.follower_blocks.blocked_id IS 'ID of the user who is blocked';

CREATE TABLE public.followers (
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    follower_id uuid NOT NULL,
    followee_id uuid NOT NULL,
    CONSTRAINT ck_followers_not_self CHECK ((follower_id <> followee_id)),
    CONSTRAINT ck_followers_status CHECK (status IN ('pending', 'accepted'))
);

COMMENT ON COLUMN public.followers.status IS 'Follow request status: pending or accepted';

COMMENT ON COLUMN public.followers.follower_id IS 'ID of the follower user (the requester)';

COMMENT ON COLUMN public.followers.followee_id IS 'ID of the followee user (the target being followed)';

CREATE TABLE public.gear (
    brand character varying(250),
    model character varying(250),
    nickname character varying(250) NOT NULL,
    gear_type integer NOT NULL,
    acquired_on date DEFAULT CURRENT_DATE CONSTRAINT gear_created_at_not_null NOT NULL,
    strava_gear_id character varying(45),
    garminconnect_gear_id character varying(45),
    initial_distance numeric(14,2) CONSTRAINT gear_initial_kms_not_null NOT NULL,
    purchase_value numeric(11,2),
    active boolean NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.gear.brand IS 'Gear brand (May include spaces)';

COMMENT ON COLUMN public.gear.model IS 'Gear model (May include spaces)';

COMMENT ON COLUMN public.gear.nickname IS 'Gear nickname (May include spaces)';

COMMENT ON COLUMN public.gear.gear_type IS 'Gear type (1 - bike, 2 - shoes, 3 - wetsuit, 4 - racquet, 5 - skis, 6 - snowboard, 7 - windsurf, 8 - water sports board)';

COMMENT ON COLUMN public.gear.acquired_on IS 'Date the user acquired the gear (today when not given)';

COMMENT ON COLUMN public.gear.strava_gear_id IS 'Strava gear ID';

COMMENT ON COLUMN public.gear.garminconnect_gear_id IS 'Garmin Connect gear ID';

COMMENT ON COLUMN public.gear.initial_distance IS 'Distance of the gear before it was tracked, in meters';

COMMENT ON COLUMN public.gear.purchase_value IS 'Gear purchase value';

COMMENT ON COLUMN public.gear.active IS 'Whether the gear is active (true - yes, false - no)';

COMMENT ON COLUMN public.gear.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.gear.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.gear.user_id IS 'User ID that the gear belongs to';

CREATE TABLE public.gear_component_deletions (
    record_id uuid NOT NULL,
    deleted_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.gear_component_deletions.record_id IS 'The id the deleted record had';

COMMENT ON COLUMN public.gear_component_deletions.deleted_at IS 'When the record was deleted';

COMMENT ON COLUMN public.gear_component_deletions.user_id IS 'Owner of the deleted record';

CREATE TABLE public.gear_components (
    type character varying(250) NOT NULL,
    brand character varying(250) NOT NULL,
    model character varying(250) NOT NULL,
    purchase_date date NOT NULL,
    retired_date date,
    expected_usage integer,
    purchase_value numeric(11,2),
    active boolean NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    gear_id uuid NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.gear_components.type IS 'Type of gear component';

COMMENT ON COLUMN public.gear_components.brand IS 'Gear component brand (May include spaces)';

COMMENT ON COLUMN public.gear_components.model IS 'Gear component model (May include spaces)';

COMMENT ON COLUMN public.gear_components.purchase_date IS 'Gear component purchase date (Date)';

COMMENT ON COLUMN public.gear_components.retired_date IS 'Gear component retired date (Date)';

COMMENT ON COLUMN public.gear_components.expected_usage IS 'Wear threshold of the gear component: meters for a distance-tracked gear, seconds for a time-tracked one';

COMMENT ON COLUMN public.gear_components.purchase_value IS 'Purchase value of the gear component';

COMMENT ON COLUMN public.gear_components.active IS 'Whether the gear component is active (true - yes, false - no)';

COMMENT ON COLUMN public.gear_components.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.gear_components.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.gear_components.created_at IS 'When the component was created';

COMMENT ON COLUMN public.gear_components.gear_id IS 'Gear ID associated with this component';

COMMENT ON COLUMN public.gear_components.user_id IS 'User ID that the gear component belongs to';

CREATE TABLE public.gear_deletions (
    record_id uuid NOT NULL,
    deleted_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.gear_deletions.record_id IS 'The id the deleted record had';

COMMENT ON COLUMN public.gear_deletions.deleted_at IS 'When the record was deleted';

COMMENT ON COLUMN public.gear_deletions.user_id IS 'Owner of the deleted record';

CREATE TABLE public.health_fasting (
    fast_start_time timestamp with time zone NOT NULL,
    fast_end_time timestamp with time zone,
    target_duration_seconds integer,
    actual_duration_seconds integer,
    fasting_type character varying(20),
    status character varying(20) NOT NULL,
    notes character varying(500),
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_fasting.fast_start_time IS 'Start time of fast';

COMMENT ON COLUMN public.health_fasting.fast_end_time IS 'End time of fast (null if ongoing)';

COMMENT ON COLUMN public.health_fasting.target_duration_seconds IS 'Target fasting duration in seconds';

COMMENT ON COLUMN public.health_fasting.actual_duration_seconds IS 'Actual fasting duration in seconds';

COMMENT ON COLUMN public.health_fasting.fasting_type IS 'Type of fasting protocol (16:8, 18:6, etc.)';

COMMENT ON COLUMN public.health_fasting.status IS 'Status: in_progress, completed, broken, cancelled';

COMMENT ON COLUMN public.health_fasting.notes IS 'Optional notes about the fasting session';

COMMENT ON COLUMN public.health_fasting.source IS 'Data source (manual, garmin, etc.)';

COMMENT ON COLUMN public.health_fasting.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.health_fasting.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.health_fasting.user_id IS 'User ID that the health_fasting belongs';

CREATE TABLE public.health_poop (
    date_time timestamp with time zone NOT NULL,
    bristol_type integer,
    color character varying(50),
    notes character varying(500),
    source character varying(250) DEFAULT 'manual'::character varying NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_poop.date_time IS 'Date and time of bowel movement';

COMMENT ON COLUMN public.health_poop.bristol_type IS 'Bristol Stool Scale type (1-7)';

COMMENT ON COLUMN public.health_poop.color IS 'Stool color description';

COMMENT ON COLUMN public.health_poop.notes IS 'Optional notes about the bowel movement';

COMMENT ON COLUMN public.health_poop.source IS 'Source of the health poop data';

COMMENT ON COLUMN public.health_poop.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.health_poop.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.health_poop.user_id IS 'User ID that the health_poop belongs';

CREATE TABLE public.health_record_deletions (
    record_id uuid NOT NULL,
    deleted_at timestamp with time zone DEFAULT now() NOT NULL,
    record_type character varying(50) NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_record_deletions.record_id IS 'The id the deleted record had';

COMMENT ON COLUMN public.health_record_deletions.deleted_at IS 'When the record was deleted';

COMMENT ON COLUMN public.health_record_deletions.record_type IS 'Sync type of the deleted record, e.g. health_weight';

COMMENT ON COLUMN public.health_record_deletions.user_id IS 'Owner of the deleted record';

CREATE TABLE public.health_sleep (
    date date NOT NULL,
    sleep_start_time_gmt timestamp with time zone,
    sleep_end_time_gmt timestamp with time zone,
    sleep_start_time_local timestamp with time zone,
    sleep_end_time_local timestamp with time zone,
    total_sleep_seconds integer,
    nap_time_seconds integer,
    unmeasurable_sleep_seconds integer,
    deep_sleep_seconds integer,
    light_sleep_seconds integer,
    rem_sleep_seconds integer,
    awake_sleep_seconds integer,
    avg_heart_rate integer,
    min_heart_rate integer,
    max_heart_rate integer,
    avg_spo2_percent integer,
    lowest_spo2_percent integer,
    highest_spo2_percent integer,
    avg_respiration integer,
    lowest_respiration integer,
    highest_respiration integer,
    avg_stress_level integer,
    awake_count integer,
    restless_moments_count integer,
    sleep_score_overall integer,
    sleep_score_duration character varying(50),
    sleep_score_quality character varying(50),
    garminconnect_sleep_id character varying(250),
    sleep_stages json,
    source character varying(250) DEFAULT 'manual'::character varying NOT NULL,
    hrv_status character varying(50),
    resting_heart_rate integer,
    avg_skin_temp_deviation numeric(10,2),
    awake_count_score character varying(50),
    rem_percentage_score character varying(50),
    deep_percentage_score character varying(50),
    light_percentage_score character varying(50),
    avg_sleep_stress integer,
    sleep_stress_score character varying(50),
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_sleep.date IS 'Calendar date of the sleep session';

COMMENT ON COLUMN public.health_sleep.sleep_start_time_gmt IS 'Start time of sleep in GMT';

COMMENT ON COLUMN public.health_sleep.sleep_end_time_gmt IS 'End time of sleep in GMT';

COMMENT ON COLUMN public.health_sleep.sleep_start_time_local IS 'Start time of sleep in local time';

COMMENT ON COLUMN public.health_sleep.sleep_end_time_local IS 'End time of sleep in local time';

COMMENT ON COLUMN public.health_sleep.total_sleep_seconds IS 'Total duration of sleep in seconds';

COMMENT ON COLUMN public.health_sleep.nap_time_seconds IS 'Duration of naps in seconds';

COMMENT ON COLUMN public.health_sleep.unmeasurable_sleep_seconds IS 'Unmeasurable sleep duration in seconds';

COMMENT ON COLUMN public.health_sleep.deep_sleep_seconds IS 'Duration of deep sleep in seconds';

COMMENT ON COLUMN public.health_sleep.light_sleep_seconds IS 'Duration of light sleep in seconds';

COMMENT ON COLUMN public.health_sleep.rem_sleep_seconds IS 'Duration of REM sleep in seconds';

COMMENT ON COLUMN public.health_sleep.awake_sleep_seconds IS 'Duration of awake time in seconds';

COMMENT ON COLUMN public.health_sleep.avg_heart_rate IS 'Average heart rate during sleep';

COMMENT ON COLUMN public.health_sleep.min_heart_rate IS 'Minimum heart rate during sleep';

COMMENT ON COLUMN public.health_sleep.max_heart_rate IS 'Maximum heart rate during sleep';

COMMENT ON COLUMN public.health_sleep.avg_spo2_percent IS 'Average SpO2 oxygen saturation percentage';

COMMENT ON COLUMN public.health_sleep.lowest_spo2_percent IS 'Lowest SpO2 reading during sleep';

COMMENT ON COLUMN public.health_sleep.highest_spo2_percent IS 'Highest SpO2 reading during sleep';

COMMENT ON COLUMN public.health_sleep.avg_respiration IS 'Average respiration rate';

COMMENT ON COLUMN public.health_sleep.lowest_respiration IS 'Lowest respiration rate';

COMMENT ON COLUMN public.health_sleep.highest_respiration IS 'Highest respiration rate';

COMMENT ON COLUMN public.health_sleep.avg_stress_level IS 'Average stress level during sleep';

COMMENT ON COLUMN public.health_sleep.awake_count IS 'Number of times awakened during sleep';

COMMENT ON COLUMN public.health_sleep.restless_moments_count IS 'Count of restless moments';

COMMENT ON COLUMN public.health_sleep.sleep_score_overall IS 'Overall sleep score (0-100)';

COMMENT ON COLUMN public.health_sleep.sleep_score_duration IS 'Sleep duration score (e.g., GOOD, EXCELLENT, POOR)';

COMMENT ON COLUMN public.health_sleep.sleep_score_quality IS 'Sleep quality score';

COMMENT ON COLUMN public.health_sleep.garminconnect_sleep_id IS 'External Garmin Connect sleep ID';

COMMENT ON COLUMN public.health_sleep.sleep_stages IS 'List of sleep stage intervals as JSON';

COMMENT ON COLUMN public.health_sleep.source IS 'Source of the health sleep data';

COMMENT ON COLUMN public.health_sleep.hrv_status IS 'Heart rate variability status';

COMMENT ON COLUMN public.health_sleep.resting_heart_rate IS 'Resting heart rate during sleep';

COMMENT ON COLUMN public.health_sleep.avg_skin_temp_deviation IS 'Average skin temperature deviation during sleep in Celsius';

COMMENT ON COLUMN public.health_sleep.awake_count_score IS 'Awake count score';

COMMENT ON COLUMN public.health_sleep.rem_percentage_score IS 'REM sleep percentage score';

COMMENT ON COLUMN public.health_sleep.deep_percentage_score IS 'Deep sleep percentage score';

COMMENT ON COLUMN public.health_sleep.light_percentage_score IS 'Light sleep percentage score';

COMMENT ON COLUMN public.health_sleep.avg_sleep_stress IS 'Average sleep stress level';

COMMENT ON COLUMN public.health_sleep.sleep_stress_score IS 'Sleep stress score';

COMMENT ON COLUMN public.health_sleep.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.health_sleep.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.health_sleep.user_id IS 'User ID that the health_sleep belongs';

CREATE TABLE public.health_steps (
    date date NOT NULL,
    steps integer NOT NULL,
    source character varying(250) DEFAULT 'manual'::character varying NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_steps.date IS 'Health steps date (date)';

COMMENT ON COLUMN public.health_steps.steps IS 'Number of steps taken';

COMMENT ON COLUMN public.health_steps.source IS 'Source of the health steps data';

COMMENT ON COLUMN public.health_steps.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.health_steps.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.health_steps.user_id IS 'User ID that the health_steps belongs';

CREATE TABLE public.health_targets (
    weight_kg numeric(10,2),
    steps integer,
    sleep_seconds integer,
    fasting_seconds integer,
    water_ml numeric(10,2),
    poop_count integer,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_targets.weight_kg IS 'Weight in kg';

COMMENT ON COLUMN public.health_targets.steps IS 'Number of steps taken';

COMMENT ON COLUMN public.health_targets.sleep_seconds IS 'Target sleep duration in seconds';

COMMENT ON COLUMN public.health_targets.fasting_seconds IS 'Target fasting duration in seconds';

COMMENT ON COLUMN public.health_targets.water_ml IS 'Target daily water intake in milliliters';

COMMENT ON COLUMN public.health_targets.poop_count IS 'Target daily bowel movement count';

COMMENT ON COLUMN public.health_targets.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.health_targets.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.health_targets.user_id IS 'User ID that the health_target belongs';

CREATE TABLE public.health_water (
    date date NOT NULL,
    amount_ml numeric(10,2) NOT NULL,
    source character varying(250) DEFAULT 'manual'::character varying NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_water.date IS 'Health water intake date (date)';

COMMENT ON COLUMN public.health_water.amount_ml IS 'Water consumed in milliliters';

COMMENT ON COLUMN public.health_water.source IS 'Source of the health water data';

COMMENT ON COLUMN public.health_water.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.health_water.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.health_water.user_id IS 'User ID that the health_water belongs';

CREATE TABLE public.health_weight (
    date date NOT NULL,
    weight_kg numeric(10,2) CONSTRAINT health_weight_weight_not_null NOT NULL,
    bmi numeric(10,2),
    body_fat_percent numeric(10,2),
    body_water_percent numeric(10,2),
    bone_mass_kg numeric(10,2),
    muscle_mass_kg numeric(10,2),
    physique_rating integer,
    visceral_fat numeric(10,2),
    metabolic_age integer,
    source character varying(250) DEFAULT 'manual'::character varying NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.health_weight.date IS 'Health weight date (date)';

COMMENT ON COLUMN public.health_weight.weight_kg IS 'Weight in kg';

COMMENT ON COLUMN public.health_weight.bmi IS 'Body mass index (BMI)';

COMMENT ON COLUMN public.health_weight.body_fat_percent IS 'Body fat percentage';

COMMENT ON COLUMN public.health_weight.body_water_percent IS 'Body hydration percentage';

COMMENT ON COLUMN public.health_weight.bone_mass_kg IS 'Bone mass in kg';

COMMENT ON COLUMN public.health_weight.muscle_mass_kg IS 'Muscle mass in kg';

COMMENT ON COLUMN public.health_weight.physique_rating IS 'Physique rating';

COMMENT ON COLUMN public.health_weight.visceral_fat IS 'Visceral fat rating';

COMMENT ON COLUMN public.health_weight.metabolic_age IS 'Metabolic age';

COMMENT ON COLUMN public.health_weight.source IS 'Source of the health weight data';

COMMENT ON COLUMN public.health_weight.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.health_weight.updated_at IS 'When the record last changed';

COMMENT ON COLUMN public.health_weight.user_id IS 'User ID that the health_weight belongs';

CREATE TABLE public.identity_providers (
    name character varying(100) NOT NULL,
    slug character varying(50) NOT NULL,
    provider_type character varying(50) NOT NULL,
    enabled boolean NOT NULL,
    client_id character varying(512),
    client_secret character varying(512),
    issuer_url character varying(500),
    authorization_endpoint character varying(500),
    token_endpoint character varying(500),
    userinfo_endpoint character varying(500),
    scopes character varying(500),
    icon character varying(500),
    auto_create_users boolean NOT NULL,
    sync_user_info boolean NOT NULL,
    user_mapping json,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    icon_uploaded boolean DEFAULT false NOT NULL,
    link_by_email boolean DEFAULT false NOT NULL,
    sync_email boolean DEFAULT false NOT NULL,
    id uuid NOT NULL
);

COMMENT ON COLUMN public.identity_providers.name IS 'Display name of the IdP';

COMMENT ON COLUMN public.identity_providers.slug IS 'URL-safe identifier';

COMMENT ON COLUMN public.identity_providers.provider_type IS 'Type: oidc, oauth2';

COMMENT ON COLUMN public.identity_providers.enabled IS 'Whether this provider is enabled';

COMMENT ON COLUMN public.identity_providers.client_id IS 'OAuth2/OIDC client ID (encrypted)';

COMMENT ON COLUMN public.identity_providers.client_secret IS 'OAuth2/OIDC client secret (encrypted)';

COMMENT ON COLUMN public.identity_providers.issuer_url IS 'OIDC issuer/discovery URL';

COMMENT ON COLUMN public.identity_providers.authorization_endpoint IS 'OAuth2/OIDC authorization endpoint';

COMMENT ON COLUMN public.identity_providers.token_endpoint IS 'OAuth2/OIDC token endpoint';

COMMENT ON COLUMN public.identity_providers.userinfo_endpoint IS 'OIDC userinfo endpoint';

COMMENT ON COLUMN public.identity_providers.scopes IS 'OAuth2/OIDC scopes to request';

COMMENT ON COLUMN public.identity_providers.icon IS 'Icon name (FontAwesome) or custom URL';

COMMENT ON COLUMN public.identity_providers.auto_create_users IS 'Automatically create users on first login';

COMMENT ON COLUMN public.identity_providers.sync_user_info IS 'Sync the mapped profile fields, except the email, on each login';

COMMENT ON COLUMN public.identity_providers.user_mapping IS 'JSON mapping of IdP claims to user fields';

COMMENT ON COLUMN public.identity_providers.created_at IS 'When this provider was created';

COMMENT ON COLUMN public.identity_providers.updated_at IS 'When this provider was last updated';

COMMENT ON COLUMN public.identity_providers.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.identity_providers.icon_uploaded IS 'Whether an uploaded icon is stored and shown instead of icon';

COMMENT ON COLUMN public.identity_providers.link_by_email IS 'Link a sign-in with no link to the local account that has the same verified email';

COMMENT ON COLUMN public.identity_providers.sync_email IS 'Sync the verified email on each login';

CREATE TABLE public.idp_session_tokens (
    session_id uuid NOT NULL,
    refresh_token text,
    access_token_expires_at timestamp with time zone,
    refresh_token_updated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    id_token text,
    idp_sid character varying(255),
    id uuid NOT NULL,
    idp_id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.idp_session_tokens.session_id IS 'Endurain session the sign-in created; no foreign key, so the token outlives the session row';

COMMENT ON COLUMN public.idp_session_tokens.refresh_token IS 'Encrypted refresh token';

COMMENT ON COLUMN public.idp_session_tokens.access_token_expires_at IS 'Access token expiry time';

COMMENT ON COLUMN public.idp_session_tokens.refresh_token_updated_at IS 'Last refresh token update';

COMMENT ON COLUMN public.idp_session_tokens.created_at IS 'When the session signed in through the provider';

COMMENT ON COLUMN public.idp_session_tokens.id_token IS 'Encrypted ID token the provider issued at sign-in';

COMMENT ON COLUMN public.idp_session_tokens.idp_sid IS 'Provider session id (sid) of the verified ID token, named by back-channel logout';

COMMENT ON COLUMN public.idp_session_tokens.idp_id IS 'Identity Provider ID';

COMMENT ON COLUMN public.idp_session_tokens.user_id IS 'User ID';

CREATE TABLE public.mail_settings (
    id integer NOT NULL,
    host character varying(253),
    port integer DEFAULT 587 NOT NULL,
    security character varying(10) DEFAULT 'starttls'::character varying NOT NULL,
    username character varying(320),
    password character varying(512),
    from_address character varying(320),
    version integer DEFAULT 1 NOT NULL,
    CONSTRAINT mail_settings_security_check CHECK (security IN ('starttls', 'ssl', 'none')),
    CONSTRAINT mail_settings_single_row_check CHECK ((id = 1))
);

COMMENT ON COLUMN public.mail_settings.host IS 'Mail server hostname (NULL - mail disabled)';

COMMENT ON COLUMN public.mail_settings.port IS 'Mail server port';

COMMENT ON COLUMN public.mail_settings.security IS 'Connection security (starttls, ssl, none)';

COMMENT ON COLUMN public.mail_settings.username IS 'Mail server authentication username';

COMMENT ON COLUMN public.mail_settings.password IS 'Mail server authentication password (encrypted)';

COMMENT ON COLUMN public.mail_settings.from_address IS 'Sender address (NULL - the username is used)';

COMMENT ON COLUMN public.mail_settings.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

CREATE SEQUENCE public.mail_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.mail_settings_id_seq OWNED BY public.mail_settings.id;

CREATE TABLE public.mfa_backup_codes (
    code_hash character varying(255) NOT NULL,
    used boolean NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.mfa_backup_codes.code_hash IS 'Argon2 hash of the backup code';

COMMENT ON COLUMN public.mfa_backup_codes.used IS 'Whether this code has been consumed';

COMMENT ON COLUMN public.mfa_backup_codes.used_at IS 'When this code was used';

COMMENT ON COLUMN public.mfa_backup_codes.created_at IS 'When this code was generated';

COMMENT ON COLUMN public.mfa_backup_codes.expires_at IS 'Optional expiry for code rotation policy';

COMMENT ON COLUMN public.mfa_backup_codes.user_id IS 'User who owns this backup code';

CREATE TABLE public.mfa_factors (
    type character varying(16) NOT NULL,
    credential character varying(512) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    last_used_at timestamp with time zone,
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    CONSTRAINT ck_mfa_factors_type CHECK (((type)::text = 'totp'::text))
);

COMMENT ON COLUMN public.mfa_factors.type IS 'Factor type: totp';

COMMENT ON COLUMN public.mfa_factors.credential IS 'Fernet-encrypted factor secret';

COMMENT ON COLUMN public.mfa_factors.created_at IS 'When the factor was enrolled';

COMMENT ON COLUMN public.mfa_factors.last_used_at IS 'When the factor last verified a sign-in or step-up';

COMMENT ON COLUMN public.mfa_factors.user_id IS 'FK to users';

CREATE TABLE public.migrations (
    id integer NOT NULL,
    name character varying(250) NOT NULL,
    description character varying(2500) NOT NULL,
    executed boolean NOT NULL
);

COMMENT ON COLUMN public.migrations.name IS 'Migration name';

COMMENT ON COLUMN public.migrations.description IS 'Migration description';

COMMENT ON COLUMN public.migrations.executed IS 'Whether the migration was executed';

CREATE SEQUENCE public.migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.migrations_id_seq OWNED BY public.migrations.id;

CREATE TABLE public.notifications (
    type integer NOT NULL,
    options json,
    read boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    source_event_id character varying(36),
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.notifications.type IS 'Notification type';

COMMENT ON COLUMN public.notifications.options IS 'Notification options (JSON)';

COMMENT ON COLUMN public.notifications.read IS 'Has the notification been read (True) or not (False)';

COMMENT ON COLUMN public.notifications.created_at IS 'Notification creation date (DateTime)';

COMMENT ON COLUMN public.notifications.source_event_id IS 'Durable event ID used to make event-driven creation idempotent';

COMMENT ON COLUMN public.notifications.user_id IS 'User ID that the notification belongs to';

CREATE TABLE public.oauth_states (
    id character varying(64) NOT NULL,
    code_challenge character varying(128),
    code_challenge_method character varying(10),
    nonce text NOT NULL,
    redirect_path character varying(500),
    client_type character varying(10) NOT NULL,
    ip_address character varying(45),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used boolean NOT NULL,
    browser_binding_hash character varying(64),
    idp_code_verifier text,
    purpose character varying(16) NOT NULL,
    session_id uuid,
    action character varying(32),
    security_generation integer,
    ends_other_sessions boolean DEFAULT false NOT NULL,
    idp_id uuid,
    user_id uuid
);

COMMENT ON COLUMN public.oauth_states.id IS 'State parameter itself (secrets.token_urlsafe(32))';

COMMENT ON COLUMN public.oauth_states.code_challenge IS 'Base64url-encoded SHA256(code_verifier)';

COMMENT ON COLUMN public.oauth_states.code_challenge_method IS 'PKCE method (only S256 supported)';

COMMENT ON COLUMN public.oauth_states.nonce IS 'Fernet-encrypted OIDC nonce for ID token validation';

COMMENT ON COLUMN public.oauth_states.redirect_path IS 'Frontend path after login';

COMMENT ON COLUMN public.oauth_states.client_type IS 'Client type: web or mobile';

COMMENT ON COLUMN public.oauth_states.ip_address IS 'Client IP address (IPv6 max length)';

COMMENT ON COLUMN public.oauth_states.created_at IS 'OAuth state creation timestamp';

COMMENT ON COLUMN public.oauth_states.expires_at IS 'Hard expiry at 10 minutes (cleanup marker)';

COMMENT ON COLUMN public.oauth_states.used IS 'True when state is consumed (prevents replay)';

COMMENT ON COLUMN public.oauth_states.browser_binding_hash IS 'SHA-256 of the browser-binding cookie (link and step-up flows)';

COMMENT ON COLUMN public.oauth_states.idp_code_verifier IS 'Fernet-encrypted PKCE verifier sent to the identity provider at the token exchange';

COMMENT ON COLUMN public.oauth_states.purpose IS 'Flow the state belongs to: login, link or step_up';

COMMENT ON COLUMN public.oauth_states.session_id IS 'Session that started a link or step-up flow';

COMMENT ON COLUMN public.oauth_states.action IS 'Sensitive operation a step-up flow authorises (step-up only)';

COMMENT ON COLUMN public.oauth_states.security_generation IS 'Account security generation the flow was started under; it is redeemed only while still current';

COMMENT ON COLUMN public.oauth_states.ends_other_sessions IS 'Whether the callback of a link ends the user''s other sessions';

COMMENT ON COLUMN public.oauth_states.idp_id IS 'Identity provider ID (may be null if mobile logic)';

COMMENT ON COLUMN public.oauth_states.user_id IS 'User ID (for link mode)';

CREATE TABLE public.password_reset_tokens (
    id uuid NOT NULL,
    token_hash character varying(128) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used boolean NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.password_reset_tokens.token_hash IS 'Hashed password reset token';

COMMENT ON COLUMN public.password_reset_tokens.created_at IS 'Token creation date (datetime)';

COMMENT ON COLUMN public.password_reset_tokens.expires_at IS 'Token expiration date (datetime)';

COMMENT ON COLUMN public.password_reset_tokens.used IS 'Token usage status';

COMMENT ON COLUMN public.password_reset_tokens.user_id IS 'User ID that the password reset token belongs to';

CREATE TABLE public.rotated_refresh_tokens (
    token_family_id uuid NOT NULL,
    hashed_token character varying(255) NOT NULL,
    rotation_count integer NOT NULL,
    rotated_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    replacement_refresh_token text,
    replacement_refresh_token_exp timestamp with time zone,
    refresh_token_exp timestamp with time zone NOT NULL,
    client_fingerprint character varying(64) NOT NULL,
    id uuid NOT NULL
);

COMMENT ON COLUMN public.rotated_refresh_tokens.token_family_id IS 'UUID of the token family';

COMMENT ON COLUMN public.rotated_refresh_tokens.hashed_token IS 'Hashed old refresh token';

COMMENT ON COLUMN public.rotated_refresh_tokens.rotation_count IS 'Which rotation this token belonged to';

COMMENT ON COLUMN public.rotated_refresh_tokens.rotated_at IS 'When this token was rotated';

COMMENT ON COLUMN public.rotated_refresh_tokens.expires_at IS 'End of the replay grace window';

COMMENT ON COLUMN public.rotated_refresh_tokens.replacement_refresh_token IS 'Fernet-encrypted replacement refresh token for idempotent in-grace replay';

COMMENT ON COLUMN public.rotated_refresh_tokens.replacement_refresh_token_exp IS 'Expiry of the replacement refresh token';

COMMENT ON COLUMN public.rotated_refresh_tokens.refresh_token_exp IS 'Expiry of the rotated refresh token; the record is purged after it';

COMMENT ON COLUMN public.rotated_refresh_tokens.client_fingerprint IS 'SHA-256 hex of the rotating client''s network and User-Agent, joined by a newline';

CREATE TABLE public.server_settings (
    id integer NOT NULL,
    public_shareable_links boolean NOT NULL,
    public_shareable_links_user_info boolean NOT NULL,
    login_photo_set boolean NOT NULL,
    num_records_per_page integer NOT NULL,
    signup_enabled boolean NOT NULL,
    signup_require_admin_approval boolean NOT NULL,
    signup_require_email_verification boolean NOT NULL,
    sso_enabled boolean NOT NULL,
    local_login_enabled boolean NOT NULL,
    sso_auto_redirect boolean NOT NULL,
    tileserver_url character varying NOT NULL,
    tileserver_attribution character varying NOT NULL,
    map_background_color character varying NOT NULL,
    password_length_regular_users integer DEFAULT 15 NOT NULL,
    password_length_admin_users integer DEFAULT 15 NOT NULL,
    tileserver_api_key character varying(512),
    units character varying(20) CONSTRAINT server_settings_units_new_not_null NOT NULL,
    currency character varying(20) CONSTRAINT server_settings_currency_new_not_null NOT NULL,
    tileserver_regenerate_thumbnails_on_change boolean CONSTRAINT server_settings_tileserver_regenerate_thumbnails_on_ch_not_null NOT NULL,
    geocoding_service character varying(20) DEFAULT 'nominatim'::character varying NOT NULL,
    geocoding_host character varying(253),
    geocoding_use_https boolean DEFAULT true NOT NULL,
    geocoding_rate_limit double precision DEFAULT 1.0 NOT NULL,
    geocoding_api_key character varying(512),
    session_idle_timeout_enabled boolean DEFAULT false NOT NULL,
    session_idle_timeout_hours integer DEFAULT 1 NOT NULL,
    session_absolute_timeout_hours integer DEFAULT 720 NOT NULL,
    access_token_expire_minutes integer DEFAULT 15 NOT NULL,
    refresh_token_expire_days integer DEFAULT 7 NOT NULL,
    read_notification_retention_days integer DEFAULT 90 NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    api_key_max_lifetime_days integer DEFAULT 365 NOT NULL,
    password_breach_check_enabled boolean DEFAULT false NOT NULL,
    signup_sso_enabled boolean DEFAULT false NOT NULL,
    require_mfa character varying(20) DEFAULT 'off'::character varying NOT NULL,
    CONSTRAINT access_token_expire_minutes_check CHECK (((access_token_expire_minutes >= 1) AND (access_token_expire_minutes <= 1440))),
    CONSTRAINT api_key_max_lifetime_days_check CHECK (((api_key_max_lifetime_days >= 1) AND (api_key_max_lifetime_days <= 3650))),
    CONSTRAINT geocoding_rate_limit_check CHECK (((geocoding_rate_limit >= (0)::double precision) AND (geocoding_rate_limit <= (100)::double precision))),
    CONSTRAINT geocoding_service_check CHECK (geocoding_service IN ('nominatim', 'photon', 'geocode')),
    CONSTRAINT read_notification_retention_days_check CHECK (((read_notification_retention_days >= 0) AND (read_notification_retention_days <= 3650))),
    CONSTRAINT refresh_token_expire_days_check CHECK (((refresh_token_expire_days >= 1) AND (refresh_token_expire_days <= 365))),
    CONSTRAINT require_mfa_check CHECK (require_mfa IN ('off', 'administrators', 'everyone')),
    CONSTRAINT session_absolute_not_below_idle_check CHECK ((session_absolute_timeout_hours >= session_idle_timeout_hours)),
    CONSTRAINT session_absolute_timeout_hours_check CHECK (((session_absolute_timeout_hours >= 1) AND (session_absolute_timeout_hours <= 8760))),
    CONSTRAINT session_idle_timeout_hours_check CHECK (((session_idle_timeout_hours >= 1) AND (session_idle_timeout_hours <= 8760))),
    CONSTRAINT single_row_check CHECK ((id = 1))
);

COMMENT ON COLUMN public.server_settings.public_shareable_links IS 'Allow public shareable links (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.public_shareable_links_user_info IS 'Allow show user info on public shareable links (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.login_photo_set IS 'Is login photo set (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.num_records_per_page IS 'Number of records per page in lists';

COMMENT ON COLUMN public.server_settings.signup_enabled IS 'Allow user sign-up registration (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.signup_require_admin_approval IS 'Require admin approval for new sign-ups (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.signup_require_email_verification IS 'Require email verification for new sign-ups (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.sso_enabled IS 'Enable SSO/IdP login (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.local_login_enabled IS 'Allow local username/password login (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.sso_auto_redirect IS 'Auto-redirect to SSO if only one IdP (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.tileserver_url IS 'URL template for the map tileserver';

COMMENT ON COLUMN public.server_settings.tileserver_attribution IS 'Attribution string for the map tileserver';

COMMENT ON COLUMN public.server_settings.map_background_color IS 'Background color for the map (hex format)';

COMMENT ON COLUMN public.server_settings.password_length_regular_users IS 'Minimum password length for regular users';

COMMENT ON COLUMN public.server_settings.password_length_admin_users IS 'Minimum password length for admin users';

COMMENT ON COLUMN public.server_settings.tileserver_api_key IS 'API key encrypted for the tile server';

COMMENT ON COLUMN public.server_settings.units IS 'Units (metric, imperial)';

COMMENT ON COLUMN public.server_settings.currency IS 'Currency (euro, dollar, pound)';

COMMENT ON COLUMN public.server_settings.tileserver_regenerate_thumbnails_on_change IS 'Delete and regenerate all activity thumbnails when tile server settings change';

COMMENT ON COLUMN public.server_settings.geocoding_service IS 'Reverse-geocoding service (nominatim, photon, geocode)';

COMMENT ON COLUMN public.server_settings.geocoding_host IS 'Host of the geocoding service (NULL - the service''s default host)';

COMMENT ON COLUMN public.server_settings.geocoding_use_https IS 'Address the geocoding host over HTTPS (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.geocoding_rate_limit IS 'Maximum geocoding requests per second (0 disables throttling)';

COMMENT ON COLUMN public.server_settings.geocoding_api_key IS 'API key encrypted for the geocoding service';

COMMENT ON COLUMN public.server_settings.session_idle_timeout_enabled IS 'Enforce the session idle timeout (true - yes, false - no); the absolute timeout always applies';

COMMENT ON COLUMN public.server_settings.session_idle_timeout_hours IS 'Hours of inactivity after which a session ends';

COMMENT ON COLUMN public.server_settings.session_absolute_timeout_hours IS 'Hours after which a session ends whatever its activity';

COMMENT ON COLUMN public.server_settings.access_token_expire_minutes IS 'Access token lifetime in minutes';

COMMENT ON COLUMN public.server_settings.refresh_token_expire_days IS 'Refresh token lifetime in days';

COMMENT ON COLUMN public.server_settings.read_notification_retention_days IS 'Days after which read notifications are purged (0 - never)';

COMMENT ON COLUMN public.server_settings.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.server_settings.api_key_max_lifetime_days IS 'Longest lifetime of a new API key, and its default, in days';

COMMENT ON COLUMN public.server_settings.password_breach_check_enabled IS 'Refuse new passwords found in a known data breach (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.signup_sso_enabled IS 'Allow identity providers to create accounts at first sign-in (true - yes, false - no)';

COMMENT ON COLUMN public.server_settings.require_mfa IS 'Require MFA of accounts without it (off, administrators, everyone)';

CREATE SEQUENCE public.server_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.server_settings_id_seq OWNED BY public.server_settings.id;

CREATE TABLE public.sign_up_tokens (
    id uuid NOT NULL,
    token_hash character varying(128) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used boolean NOT NULL,
    email character varying(250),
    previous_email character varying(250),
    security_generation integer,
    change_id uuid,
    revert_until timestamp with time zone,
    confirmed_at timestamp with time zone,
    reverted_at timestamp with time zone,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.sign_up_tokens.token_hash IS 'Hashed sign up token';

COMMENT ON COLUMN public.sign_up_tokens.created_at IS 'Token creation date (datetime)';

COMMENT ON COLUMN public.sign_up_tokens.expires_at IS 'Token expiration date (datetime)';

COMMENT ON COLUMN public.sign_up_tokens.used IS 'Token usage status';

COMMENT ON COLUMN public.sign_up_tokens.email IS 'Email address the token proves (empty on tokens issued before the column existed)';

COMMENT ON COLUMN public.sign_up_tokens.previous_email IS 'Account email address when an email change was requested (email-change tokens only)';

COMMENT ON COLUMN public.sign_up_tokens.security_generation IS 'Account security generation an email-change token was issued under (email-change tokens only)';

COMMENT ON COLUMN public.sign_up_tokens.change_id IS 'Identifier of the email change the token belongs to (email-change tokens only)';

COMMENT ON COLUMN public.sign_up_tokens.revert_until IS 'End of the email change''s revert window (email-change tokens only)';

COMMENT ON COLUMN public.sign_up_tokens.confirmed_at IS 'When the token was confirmed, or the email change it records was applied';

COMMENT ON COLUMN public.sign_up_tokens.reverted_at IS 'When the email change''s revert link was used (email-change tokens only)';

COMMENT ON COLUMN public.sign_up_tokens.user_id IS 'User ID that the sign up token belongs to';

CREATE TABLE public.users (
    name character varying(250) NOT NULL,
    username character varying(250) NOT NULL,
    email character varying(250) NOT NULL,
    city character varying(250),
    birthdate date,
    preferred_language character varying(35) NOT NULL,
    photo_path character varying(250),
    height integer,
    email_verified boolean NOT NULL,
    pending_admin_approval boolean NOT NULL,
    active boolean NOT NULL,
    max_heart_rate integer,
    gender character varying(20) CONSTRAINT users_gender_new_not_null NOT NULL,
    access_type character varying(20) CONSTRAINT users_access_type_new_not_null NOT NULL,
    first_day_of_week character varying(20) CONSTRAINT users_first_day_of_week_new_not_null NOT NULL,
    units character varying(20) CONSTRAINT users_units_new_not_null NOT NULL,
    currency character varying(20) CONSTRAINT users_currency_new_not_null NOT NULL,
    timezone character varying(250),
    version integer DEFAULT 1 NOT NULL,
    deletion_requested_at timestamp with time zone,
    deletion_attempts integer DEFAULT 0 NOT NULL,
    deactivated_at timestamp with time zone,
    weight_units character varying(20),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    CONSTRAINT ck_users_access_type CHECK (access_type IN ('regular', 'admin'))
);

COMMENT ON COLUMN public.users.name IS 'User real name (May include spaces)';

COMMENT ON COLUMN public.users.username IS 'User username (letters, numbers, and dots allowed)';

COMMENT ON COLUMN public.users.email IS 'User email (max 250 characters)';

COMMENT ON COLUMN public.users.city IS 'User city';

COMMENT ON COLUMN public.users.birthdate IS 'User birthdate (date)';

COMMENT ON COLUMN public.users.preferred_language IS 'User preferred BCP 47 language tag (en, pt-PT, zh-Hans, others)';

COMMENT ON COLUMN public.users.photo_path IS 'User photo path';

COMMENT ON COLUMN public.users.height IS 'User height in centimeters';

COMMENT ON COLUMN public.users.email_verified IS 'Whether the user''s email address has been verified (true - yes, false - no)';

COMMENT ON COLUMN public.users.pending_admin_approval IS 'Whether the user is pending admin approval for activation (true - yes, false - no)';

COMMENT ON COLUMN public.users.active IS 'Whether the user is active (true - yes, false - no)';

COMMENT ON COLUMN public.users.max_heart_rate IS 'User maximum heart rate (bpm)';

COMMENT ON COLUMN public.users.gender IS 'User gender (male, female, unspecified)';

COMMENT ON COLUMN public.users.access_type IS 'User type (regular, admin)';

COMMENT ON COLUMN public.users.first_day_of_week IS 'User first day of week (sunday, monday, etc.)';

COMMENT ON COLUMN public.users.units IS 'User units (metric, imperial)';

COMMENT ON COLUMN public.users.currency IS 'User currency (euro, dollar, pound)';

COMMENT ON COLUMN public.users.timezone IS 'User IANA timezone, used as the fallback for activities with no GPS track';

COMMENT ON COLUMN public.users.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.users.deletion_requested_at IS 'When the account was queued for deletion; null for an account that is not being deleted';

COMMENT ON COLUMN public.users.deletion_attempts IS 'How many times the sweep queued this account''s deletion again';

COMMENT ON COLUMN public.users.deactivated_at IS 'When the account was deactivated by an administrator or a deletion request; null for an active account and for a sign-up not yet verified or approved';

COMMENT ON COLUMN public.users.weight_units IS 'User weight units override (metric - kg, imperial - lb), null follows units';

COMMENT ON COLUMN public.users.created_at IS 'When the account was created; accounts that predate the column carry the migration time';

CREATE TABLE public.users_api_keys (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    key_prefix character varying(8) NOT NULL,
    key_hash character varying(64) NOT NULL,
    scopes text NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_used_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL,
    is_active boolean NOT NULL,
    revoked_at timestamp with time zone,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.users_api_keys.id IS 'Unique key identifier (UUID4)';

COMMENT ON COLUMN public.users_api_keys.name IS 'User-friendly label for the key';

COMMENT ON COLUMN public.users_api_keys.key_prefix IS 'First 8 chars of the random key part, used for UI identification';

COMMENT ON COLUMN public.users_api_keys.key_hash IS 'SHA-256 hex digest of the full raw key';

COMMENT ON COLUMN public.users_api_keys.scopes IS 'JSON-encoded list of granted scope strings';

COMMENT ON COLUMN public.users_api_keys.expires_at IS 'Key expiration timestamp';

COMMENT ON COLUMN public.users_api_keys.last_used_at IS 'Timestamp of last successful authentication';

COMMENT ON COLUMN public.users_api_keys.created_at IS 'Key creation timestamp';

COMMENT ON COLUMN public.users_api_keys.is_active IS 'Whether the key is active. False = revoked (soft delete)';

COMMENT ON COLUMN public.users_api_keys.revoked_at IS 'When the key was revoked; null while it has not been';

COMMENT ON COLUMN public.users_api_keys.user_id IS 'User ID that the API key belongs to';

CREATE TABLE public.users_default_gear (
    version integer DEFAULT 1 NOT NULL,
    id uuid NOT NULL,
    run_gear_id uuid,
    trail_run_gear_id uuid,
    virtual_run_gear_id uuid,
    ride_gear_id uuid,
    gravel_ride_gear_id uuid,
    mtb_ride_gear_id uuid,
    virtual_ride_gear_id uuid,
    ows_gear_id uuid,
    walk_gear_id uuid,
    hike_gear_id uuid,
    tennis_gear_id uuid,
    alpine_ski_gear_id uuid,
    nordic_ski_gear_id uuid,
    snowboard_gear_id uuid,
    windsurf_gear_id uuid,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.users_default_gear.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.users_default_gear.run_gear_id IS 'Gear ID that the default run activity type belongs';

COMMENT ON COLUMN public.users_default_gear.trail_run_gear_id IS 'Gear ID that the default trail run activity type belongs';

COMMENT ON COLUMN public.users_default_gear.virtual_run_gear_id IS 'Gear ID that the default virtual run activity type belongs';

COMMENT ON COLUMN public.users_default_gear.ride_gear_id IS 'Gear ID that the default ride activity type belongs';

COMMENT ON COLUMN public.users_default_gear.gravel_ride_gear_id IS 'Gear ID that the default gravel ride activity type belongs';

COMMENT ON COLUMN public.users_default_gear.mtb_ride_gear_id IS 'Gear ID that the default MTB ride activity type belongs';

COMMENT ON COLUMN public.users_default_gear.virtual_ride_gear_id IS 'Gear ID that the default virtual ride activity type belongs';

COMMENT ON COLUMN public.users_default_gear.ows_gear_id IS 'Gear ID that the default OWS activity type belongs';

COMMENT ON COLUMN public.users_default_gear.walk_gear_id IS 'Gear ID that the default walk activity type belongs';

COMMENT ON COLUMN public.users_default_gear.hike_gear_id IS 'Gear ID that the default hike activity type belongs';

COMMENT ON COLUMN public.users_default_gear.tennis_gear_id IS 'Gear ID that the default tennis activity type belongs';

COMMENT ON COLUMN public.users_default_gear.alpine_ski_gear_id IS 'Gear ID that the default alpine ski activity type belongs';

COMMENT ON COLUMN public.users_default_gear.nordic_ski_gear_id IS 'Gear ID that the default nordic ski activity type belongs';

COMMENT ON COLUMN public.users_default_gear.snowboard_gear_id IS 'Gear ID that the default snowboard activity type belongs';

COMMENT ON COLUMN public.users_default_gear.windsurf_gear_id IS 'Gear ID that the default windsurf activity type belongs';

COMMENT ON COLUMN public.users_default_gear.user_id IS 'User ID that the default gear belongs';

CREATE TABLE public.users_goals (
    "interval" character varying(250) NOT NULL,
    goal_calories integer,
    goal_activities_number integer,
    goal_distance integer,
    goal_elevation integer,
    goal_duration integer,
    activity_type character varying(50) CONSTRAINT users_goals_activity_type_new_not_null NOT NULL,
    goal_type character varying(50) CONSTRAINT users_goals_goal_type_new_not_null NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.users_goals."interval" IS 'Goal interval (e.g., ''daily'', ''weekly'', ''monthly'', ''yearly'')';

COMMENT ON COLUMN public.users_goals.goal_calories IS 'Goal calories in kcal (e.g., 5000 for 5000 kcal)';

COMMENT ON COLUMN public.users_goals.goal_activities_number IS 'Goal activities number (e.g., 5 for 5 activities)';

COMMENT ON COLUMN public.users_goals.goal_distance IS 'Goal distance in meters (e.g., 10000 for 10 km)';

COMMENT ON COLUMN public.users_goals.goal_elevation IS 'Goal elevation in meters (e.g., 1000 for 1000 m)';

COMMENT ON COLUMN public.users_goals.goal_duration IS 'Goal duration in seconds (e.g., 3600 for 1 hours)';

COMMENT ON COLUMN public.users_goals.activity_type IS 'Activity type (e.g., ''run'', ''bike'', ''swim'')';

COMMENT ON COLUMN public.users_goals.goal_type IS 'Goal type (e.g., ''calories'', ''distance'', ''duration'')';

COMMENT ON COLUMN public.users_goals.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.users_goals.created_at IS 'When the goal was created';

COMMENT ON COLUMN public.users_goals.user_id IS 'User ID that the goals belongs';

CREATE TABLE public.users_identity_providers (
    idp_subject character varying(500) NOT NULL,
    linked_at timestamp with time zone DEFAULT now() NOT NULL,
    last_login timestamp with time zone,
    id uuid NOT NULL,
    idp_id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.users_identity_providers.idp_subject IS 'Subject/ID from the identity provider';

COMMENT ON COLUMN public.users_identity_providers.linked_at IS 'When this IdP was linked to the user';

COMMENT ON COLUMN public.users_identity_providers.last_login IS 'Last login using this IdP';

COMMENT ON COLUMN public.users_identity_providers.idp_id IS 'Identity Provider ID';

COMMENT ON COLUMN public.users_identity_providers.user_id IS 'User ID';

CREATE TABLE public.users_integrations (
    strava_token character varying(512),
    strava_refresh_token character varying(512),
    strava_token_expires_at timestamp with time zone,
    strava_sync_gear boolean NOT NULL,
    garminconnect_sync_gear boolean DEFAULT false NOT NULL,
    strava_client_id character varying(512),
    strava_client_secret character varying(512),
    garminconnect_token json,
    version integer DEFAULT 1 NOT NULL,
    strava_revoked_at timestamp with time zone,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.users_integrations.strava_token IS 'Strava token after link process encrypted at rest with Fernet key';

COMMENT ON COLUMN public.users_integrations.strava_refresh_token IS 'Strava refresh token after link process encrypted at rest with Fernet key';

COMMENT ON COLUMN public.users_integrations.strava_token_expires_at IS 'Strava token expiration date';

COMMENT ON COLUMN public.users_integrations.strava_sync_gear IS 'Whether Strava gear is to be synced';

COMMENT ON COLUMN public.users_integrations.garminconnect_sync_gear IS 'Whether Garmin Connect gear is to be synced';

COMMENT ON COLUMN public.users_integrations.strava_client_id IS 'Strava client ID encrypted at rest with Fernet key';

COMMENT ON COLUMN public.users_integrations.strava_client_secret IS 'Strava client secret encrypted at rest with Fernet key';

COMMENT ON COLUMN public.users_integrations.garminconnect_token IS 'Garmin Connect token';

COMMENT ON COLUMN public.users_integrations.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.users_integrations.strava_revoked_at IS 'When Strava refused the refresh token; Strava data is deleted after the grace period';

COMMENT ON COLUMN public.users_integrations.user_id IS 'User ID that the integration belongs';

CREATE TABLE public.users_local_credentials (
    password_hash character varying(250) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    password_change_required boolean DEFAULT false NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.users_local_credentials.password_hash IS 'Local account password hash';

COMMENT ON COLUMN public.users_local_credentials.password_change_required IS 'Whether the owner must choose a new password at the next sign-in (an administrator wrote it)';

COMMENT ON COLUMN public.users_local_credentials.user_id IS 'User the credentials belong to';

CREATE TABLE public.users_privacy_settings (
    hide_activity_start_time boolean NOT NULL,
    hide_activity_location boolean NOT NULL,
    hide_activity_map boolean NOT NULL,
    hide_activity_hr boolean NOT NULL,
    hide_activity_power boolean NOT NULL,
    hide_activity_cadence boolean NOT NULL,
    hide_activity_elevation boolean NOT NULL,
    hide_activity_speed boolean NOT NULL,
    hide_activity_pace boolean NOT NULL,
    hide_activity_laps boolean NOT NULL,
    hide_activity_workout_sets_steps boolean CONSTRAINT users_privacy_settings_hide_activity_workout_sets_step_not_null NOT NULL,
    hide_activity_gear boolean NOT NULL,
    default_activity_visibility character varying(20) CONSTRAINT users_privacy_settings_default_activity_visibility_new_not_null NOT NULL,
    version integer DEFAULT 1 NOT NULL,
    discoverable boolean DEFAULT true NOT NULL,
    id uuid NOT NULL,
    user_id uuid NOT NULL
);

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_start_time IS 'Hide activity start time';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_location IS 'Hide activity location';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_map IS 'Hide activity map';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_hr IS 'Hide activity heart rate';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_power IS 'Hide activity power';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_cadence IS 'Hide activity cadence';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_elevation IS 'Hide activity elevation';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_speed IS 'Hide activity speed';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_pace IS 'Hide activity pace';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_laps IS 'Hide activity laps';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_workout_sets_steps IS 'Hide activity workout sets and steps';

COMMENT ON COLUMN public.users_privacy_settings.hide_activity_gear IS 'Hide activity gear';

COMMENT ON COLUMN public.users_privacy_settings.default_activity_visibility IS 'public, followers, private';

COMMENT ON COLUMN public.users_privacy_settings.version IS 'Optimistic-concurrency counter, surfaced to clients as the ETag';

COMMENT ON COLUMN public.users_privacy_settings.discoverable IS 'Appear in other users'' username search';

COMMENT ON COLUMN public.users_privacy_settings.user_id IS 'User ID that the privacy settings belongs';

CREATE TABLE public.users_sessions (
    id uuid NOT NULL,
    refresh_token character varying(255),
    ip_address character varying(45) NOT NULL,
    device_type character varying(45) NOT NULL,
    operating_system character varying(45) NOT NULL,
    operating_system_version character varying(45) NOT NULL,
    browser character varying(45) NOT NULL,
    browser_version character varying(45) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_activity_at timestamp with time zone NOT NULL,
    oauth_state_id character varying(64),
    tokens_exchanged boolean NOT NULL,
    token_family_id uuid NOT NULL,
    rotation_count integer NOT NULL,
    last_rotation_at timestamp with time zone,
    client_type character varying(10) NOT NULL,
    auth_time timestamp with time zone NOT NULL,
    amr json NOT NULL,
    app_redirect_uri character varying(500),
    device_hash character varying(64),
    user_id uuid NOT NULL,
    CONSTRAINT ck_users_sessions_client_type CHECK (client_type IN ('web', 'mobile'))
);

COMMENT ON COLUMN public.users_sessions.refresh_token IS 'Session hashed refresh token';

COMMENT ON COLUMN public.users_sessions.ip_address IS 'Client IP address';

COMMENT ON COLUMN public.users_sessions.device_type IS 'Device type';

COMMENT ON COLUMN public.users_sessions.operating_system IS 'Operating system';

COMMENT ON COLUMN public.users_sessions.operating_system_version IS 'Operating system version';

COMMENT ON COLUMN public.users_sessions.browser IS 'Browser';

COMMENT ON COLUMN public.users_sessions.browser_version IS 'Browser version';

COMMENT ON COLUMN public.users_sessions.created_at IS 'Session creation date (datetime)';

COMMENT ON COLUMN public.users_sessions.expires_at IS 'Session expiration date (datetime)';

COMMENT ON COLUMN public.users_sessions.last_activity_at IS 'Last activity timestamp for idle timeout';

COMMENT ON COLUMN public.users_sessions.oauth_state_id IS 'Link to OAuth state for PKCE validation';

COMMENT ON COLUMN public.users_sessions.tokens_exchanged IS 'Prevents duplicate token exchange for mobile';

COMMENT ON COLUMN public.users_sessions.token_family_id IS 'UUID identifying token family for reuse detection';

COMMENT ON COLUMN public.users_sessions.rotation_count IS 'Number of times refresh token has been rotated';

COMMENT ON COLUMN public.users_sessions.last_rotation_at IS 'Timestamp of last token rotation';

COMMENT ON COLUMN public.users_sessions.client_type IS 'Client type the session was created for: web or mobile';

COMMENT ON COLUMN public.users_sessions.auth_time IS 'When the user signed in; refresh and step-up do not change it';

COMMENT ON COLUMN public.users_sessions.amr IS 'Authentication methods of the sign-in (RFC 8176 values): pwd, fed, otp, mfa';

COMMENT ON COLUMN public.users_sessions.app_redirect_uri IS 'Native-app redirect address an SSO sign-in handed the session to';

COMMENT ON COLUMN public.users_sessions.device_hash IS 'SHA-256 hex digest of the device id the session signed in from';

COMMENT ON COLUMN public.users_sessions.user_id IS 'User ID that the session belongs';

ALTER TABLE ONLY public.activity_exercise_titles ALTER COLUMN id SET DEFAULT nextval('public.activity_exercise_titles_id_seq'::regclass);

ALTER TABLE ONLY public.mail_settings ALTER COLUMN id SET DEFAULT nextval('public.mail_settings_id_seq'::regclass);

ALTER TABLE ONLY public.migrations ALTER COLUMN id SET DEFAULT nextval('public.migrations_id_seq'::regclass);

ALTER TABLE ONLY public.server_settings ALTER COLUMN id SET DEFAULT nextval('public.server_settings_id_seq'::regclass);

ALTER TABLE ONLY public.account_security_generations
    ADD CONSTRAINT account_security_generations_pkey PRIMARY KEY (user_id);

ALTER TABLE ONLY public.activities
    ADD CONSTRAINT activities_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activities_streams
    ADD CONSTRAINT activities_streams_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_deletions
    ADD CONSTRAINT activity_deletions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_exercise_titles
    ADD CONSTRAINT activity_exercise_titles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_ingestion_jobs
    ADD CONSTRAINT activity_ingestion_jobs_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_laps
    ADD CONSTRAINT activity_laps_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_media
    ADD CONSTRAINT activity_media_media_path_key UNIQUE (media_path);

ALTER TABLE ONLY public.activity_media
    ADD CONSTRAINT activity_media_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_sets
    ADD CONSTRAINT activity_sets_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_workout_steps
    ADD CONSTRAINT activity_workout_steps_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.auth_known_devices
    ADD CONSTRAINT auth_known_devices_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.follow_request_declines
    ADD CONSTRAINT follow_request_declines_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.follower_blocks
    ADD CONSTRAINT follower_blocks_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.followers
    ADD CONSTRAINT followers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.gear_component_deletions
    ADD CONSTRAINT gear_component_deletions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.gear_components
    ADD CONSTRAINT gear_components_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.gear_deletions
    ADD CONSTRAINT gear_deletions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.gear
    ADD CONSTRAINT gear_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_fasting
    ADD CONSTRAINT health_fasting_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_poop
    ADD CONSTRAINT health_poop_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_record_deletions
    ADD CONSTRAINT health_record_deletions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_sleep
    ADD CONSTRAINT health_sleep_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_steps
    ADD CONSTRAINT health_steps_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_targets
    ADD CONSTRAINT health_targets_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_water
    ADD CONSTRAINT health_water_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.health_weight
    ADD CONSTRAINT health_weight_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.identity_providers
    ADD CONSTRAINT identity_providers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.idp_session_tokens
    ADD CONSTRAINT idp_session_tokens_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.idp_session_tokens
    ADD CONSTRAINT idp_session_tokens_session_id_key UNIQUE (session_id);

ALTER TABLE ONLY public.mail_settings
    ADD CONSTRAINT mail_settings_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mfa_backup_codes
    ADD CONSTRAINT mfa_backup_codes_code_hash_key UNIQUE (code_hash);

ALTER TABLE ONLY public.mfa_backup_codes
    ADD CONSTRAINT mfa_backup_codes_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mfa_factors
    ADD CONSTRAINT mfa_factors_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.migrations
    ADD CONSTRAINT migrations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.oauth_states
    ADD CONSTRAINT oauth_states_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.rotated_refresh_tokens
    ADD CONSTRAINT rotated_refresh_tokens_hashed_token_key UNIQUE (hashed_token);

ALTER TABLE ONLY public.rotated_refresh_tokens
    ADD CONSTRAINT rotated_refresh_tokens_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.server_settings
    ADD CONSTRAINT server_settings_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.sign_up_tokens
    ADD CONSTRAINT sign_up_tokens_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.activity_exercise_titles
    ADD CONSTRAINT uq_activity_exercise_titles_category_name UNIQUE (exercise_category, exercise_name);

ALTER TABLE ONLY public.activity_ingestion_jobs
    ADD CONSTRAINT uq_activity_ingestion_jobs_user_kind_idempotency UNIQUE (user_id, kind, idempotency_key);

ALTER TABLE ONLY public.auth_known_devices
    ADD CONSTRAINT uq_auth_known_devices_user_id_device_hash UNIQUE (user_id, device_hash);

ALTER TABLE ONLY public.follow_request_declines
    ADD CONSTRAINT uq_follow_request_declines_follower_followee UNIQUE (follower_id, followee_id);

ALTER TABLE ONLY public.follower_blocks
    ADD CONSTRAINT uq_follower_blocks_blocker_blocked UNIQUE (blocker_id, blocked_id);

ALTER TABLE ONLY public.followers
    ADD CONSTRAINT uq_followers_follower_followee UNIQUE (follower_id, followee_id);

ALTER TABLE ONLY public.gear
    ADD CONSTRAINT uq_gear_user_garminconnect_gear_id UNIQUE (user_id, garminconnect_gear_id);

ALTER TABLE ONLY public.gear
    ADD CONSTRAINT uq_gear_user_strava_gear_id UNIQUE (user_id, strava_gear_id);

ALTER TABLE ONLY public.health_sleep
    ADD CONSTRAINT uq_health_sleep_user_date UNIQUE (user_id, date);

ALTER TABLE ONLY public.health_steps
    ADD CONSTRAINT uq_health_steps_user_date UNIQUE (user_id, date);

ALTER TABLE ONLY public.health_water
    ADD CONSTRAINT uq_health_water_user_date UNIQUE (user_id, date);

ALTER TABLE ONLY public.health_weight
    ADD CONSTRAINT uq_health_weight_user_date UNIQUE (user_id, date);

ALTER TABLE ONLY public.users_identity_providers
    ADD CONSTRAINT uq_identity_links_idp_subject UNIQUE (idp_id, idp_subject);

ALTER TABLE ONLY public.users_identity_providers
    ADD CONSTRAINT uq_identity_links_user_idp UNIQUE (user_id, idp_id);

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT uq_notifications_source_event_user_type UNIQUE (source_event_id, user_id, type);

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT uq_users_default_gear_user_id UNIQUE (user_id);

ALTER TABLE ONLY public.users_goals
    ADD CONSTRAINT uq_users_goals_user_scope UNIQUE (user_id, "interval", activity_type, goal_type);

ALTER TABLE ONLY public.users_api_keys
    ADD CONSTRAINT users_api_keys_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users_goals
    ADD CONSTRAINT users_goals_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users_identity_providers
    ADD CONSTRAINT users_identity_providers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users_integrations
    ADD CONSTRAINT users_integrations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users_local_credentials
    ADD CONSTRAINT users_local_credentials_pkey PRIMARY KEY (user_id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users_privacy_settings
    ADD CONSTRAINT users_privacy_settings_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.users_sessions
    ADD CONSTRAINT users_sessions_pkey PRIMARY KEY (id);

CREATE INDEX idx_activity_ingestion_jobs_user_created ON public.activity_ingestion_jobs USING btree (user_id, created_at);

CREATE INDEX idx_user_unused_codes ON public.mfa_backup_codes USING btree (user_id, used);

CREATE INDEX ix_activities_gear_id ON public.activities USING btree (gear_id);

CREATE INDEX ix_activities_streams_activity_id ON public.activities_streams USING btree (activity_id);

CREATE INDEX ix_activities_user_id ON public.activities USING btree (user_id);

CREATE INDEX ix_activities_user_id_strava_activity_id ON public.activities USING btree (user_id, strava_activity_id);

CREATE INDEX ix_activities_user_id_updated_at_id ON public.activities USING btree (user_id, updated_at, id);

CREATE INDEX ix_activity_deletions_user_id_deleted_at_id ON public.activity_deletions USING btree (user_id, deleted_at, id);

CREATE INDEX ix_activity_ingestion_jobs_user_id ON public.activity_ingestion_jobs USING btree (user_id);

CREATE INDEX ix_activity_laps_activity_id ON public.activity_laps USING btree (activity_id);

CREATE INDEX ix_activity_media_activity_id ON public.activity_media USING btree (activity_id);

CREATE INDEX ix_activity_sets_activity_id ON public.activity_sets USING btree (activity_id);

CREATE INDEX ix_activity_workout_steps_activity_id ON public.activity_workout_steps USING btree (activity_id);

CREATE INDEX ix_auth_known_devices_last_seen_at ON public.auth_known_devices USING btree (last_seen_at);

CREATE INDEX ix_follow_request_declines_followee_id ON public.follow_request_declines USING btree (followee_id);

CREATE INDEX ix_follow_request_declines_follower_id ON public.follow_request_declines USING btree (follower_id);

CREATE INDEX ix_follower_blocks_blocked_id ON public.follower_blocks USING btree (blocked_id);

CREATE INDEX ix_follower_blocks_blocker_id ON public.follower_blocks USING btree (blocker_id);

CREATE INDEX ix_follower_blocks_id ON public.follower_blocks USING btree (id);

CREATE INDEX ix_followers_followee_id ON public.followers USING btree (followee_id);

CREATE INDEX ix_followers_follower_id ON public.followers USING btree (follower_id);

CREATE INDEX ix_followers_id ON public.followers USING btree (id);

CREATE INDEX ix_gear_component_deletions_user_id_deleted_at_id ON public.gear_component_deletions USING btree (user_id, deleted_at, id);

CREATE INDEX ix_gear_components_gear_id ON public.gear_components USING btree (gear_id);

CREATE INDEX ix_gear_components_user_id_updated_at_id ON public.gear_components USING btree (user_id, updated_at, id);

CREATE INDEX ix_gear_deletions_user_id_deleted_at_id ON public.gear_deletions USING btree (user_id, deleted_at, id);

CREATE INDEX ix_gear_user_id_updated_at_id ON public.gear USING btree (user_id, updated_at, id);

CREATE INDEX ix_health_fasting_user_id ON public.health_fasting USING btree (user_id);

CREATE INDEX ix_health_fasting_user_updated_at_id ON public.health_fasting USING btree (user_id, updated_at, id);

CREATE INDEX ix_health_poop_date_time ON public.health_poop USING btree (date_time);

CREATE INDEX ix_health_poop_user_id ON public.health_poop USING btree (user_id);

CREATE INDEX ix_health_poop_user_updated_at_id ON public.health_poop USING btree (user_id, updated_at, id);

CREATE INDEX ix_health_record_deletions_user_deleted_at_id ON public.health_record_deletions USING btree (user_id, deleted_at, id);

CREATE INDEX ix_health_sleep_date ON public.health_sleep USING btree (date);

CREATE INDEX ix_health_sleep_user_id ON public.health_sleep USING btree (user_id);

CREATE INDEX ix_health_sleep_user_updated_at_id ON public.health_sleep USING btree (user_id, updated_at, id);

CREATE INDEX ix_health_steps_date ON public.health_steps USING btree (date);

CREATE INDEX ix_health_steps_user_id ON public.health_steps USING btree (user_id);

CREATE INDEX ix_health_steps_user_updated_at_id ON public.health_steps USING btree (user_id, updated_at, id);

CREATE UNIQUE INDEX ix_health_targets_user_id ON public.health_targets USING btree (user_id);

CREATE INDEX ix_health_targets_user_updated_at_id ON public.health_targets USING btree (user_id, updated_at, id);

CREATE INDEX ix_health_water_date ON public.health_water USING btree (date);

CREATE INDEX ix_health_water_user_id ON public.health_water USING btree (user_id);

CREATE INDEX ix_health_water_user_updated_at_id ON public.health_water USING btree (user_id, updated_at, id);

CREATE INDEX ix_health_weight_date ON public.health_weight USING btree (date);

CREATE INDEX ix_health_weight_user_id ON public.health_weight USING btree (user_id);

CREATE INDEX ix_health_weight_user_updated_at_id ON public.health_weight USING btree (user_id, updated_at, id);

CREATE INDEX ix_identity_providers_enabled ON public.identity_providers USING btree (enabled);

CREATE INDEX ix_identity_providers_id ON public.identity_providers USING btree (id);

CREATE UNIQUE INDEX ix_identity_providers_slug ON public.identity_providers USING btree (slug);

CREATE INDEX ix_idp_session_tokens_idp_id ON public.idp_session_tokens USING btree (idp_id);

CREATE INDEX ix_idp_session_tokens_idp_id_idp_sid ON public.idp_session_tokens USING btree (idp_id, idp_sid);

CREATE INDEX ix_idp_session_tokens_user_id ON public.idp_session_tokens USING btree (user_id);

CREATE INDEX ix_mfa_backup_codes_used ON public.mfa_backup_codes USING btree (used);

CREATE INDEX ix_mfa_backup_codes_user_id ON public.mfa_backup_codes USING btree (user_id);

CREATE INDEX ix_mfa_factors_user_id ON public.mfa_factors USING btree (user_id);

CREATE INDEX ix_notifications_read_created_at ON public.notifications USING btree (created_at) WHERE read;

CREATE INDEX ix_notifications_user_id_created_at ON public.notifications USING btree (user_id, created_at);

CREATE INDEX ix_oauth_states_expires_at ON public.oauth_states USING btree (expires_at);

CREATE INDEX ix_oauth_states_id ON public.oauth_states USING btree (id);

CREATE INDEX ix_oauth_states_idp_id ON public.oauth_states USING btree (idp_id);

CREATE INDEX ix_oauth_states_used ON public.oauth_states USING btree (used);

CREATE INDEX ix_oauth_states_user_id ON public.oauth_states USING btree (user_id);

CREATE INDEX ix_password_reset_tokens_expires_at ON public.password_reset_tokens USING btree (expires_at);

CREATE UNIQUE INDEX ix_password_reset_tokens_token_hash ON public.password_reset_tokens USING btree (token_hash);

CREATE INDEX ix_password_reset_tokens_user_id ON public.password_reset_tokens USING btree (user_id);

CREATE INDEX ix_rotated_refresh_tokens_expires_at_with_replacement ON public.rotated_refresh_tokens USING btree (expires_at) WHERE (replacement_refresh_token IS NOT NULL);

CREATE INDEX ix_rotated_refresh_tokens_refresh_token_exp ON public.rotated_refresh_tokens USING btree (refresh_token_exp);

CREATE INDEX ix_rotated_refresh_tokens_token_family_id ON public.rotated_refresh_tokens USING btree (token_family_id);

CREATE INDEX ix_sign_up_tokens_change_id ON public.sign_up_tokens USING btree (change_id);

CREATE INDEX ix_sign_up_tokens_expires_at ON public.sign_up_tokens USING btree (expires_at);

CREATE UNIQUE INDEX ix_sign_up_tokens_token_hash ON public.sign_up_tokens USING btree (token_hash);

CREATE INDEX ix_sign_up_tokens_user_id ON public.sign_up_tokens USING btree (user_id);

CREATE UNIQUE INDEX ix_users_api_keys_key_hash ON public.users_api_keys USING btree (key_hash);

CREATE INDEX ix_users_api_keys_user_id ON public.users_api_keys USING btree (user_id);

CREATE INDEX ix_users_default_gear_alpine_ski_gear_id ON public.users_default_gear USING btree (alpine_ski_gear_id);

CREATE INDEX ix_users_default_gear_gravel_ride_gear_id ON public.users_default_gear USING btree (gravel_ride_gear_id);

CREATE INDEX ix_users_default_gear_hike_gear_id ON public.users_default_gear USING btree (hike_gear_id);

CREATE INDEX ix_users_default_gear_mtb_ride_gear_id ON public.users_default_gear USING btree (mtb_ride_gear_id);

CREATE INDEX ix_users_default_gear_nordic_ski_gear_id ON public.users_default_gear USING btree (nordic_ski_gear_id);

CREATE INDEX ix_users_default_gear_ows_gear_id ON public.users_default_gear USING btree (ows_gear_id);

CREATE INDEX ix_users_default_gear_ride_gear_id ON public.users_default_gear USING btree (ride_gear_id);

CREATE INDEX ix_users_default_gear_run_gear_id ON public.users_default_gear USING btree (run_gear_id);

CREATE INDEX ix_users_default_gear_snowboard_gear_id ON public.users_default_gear USING btree (snowboard_gear_id);

CREATE INDEX ix_users_default_gear_tennis_gear_id ON public.users_default_gear USING btree (tennis_gear_id);

CREATE INDEX ix_users_default_gear_trail_run_gear_id ON public.users_default_gear USING btree (trail_run_gear_id);

CREATE INDEX ix_users_default_gear_user_id ON public.users_default_gear USING btree (user_id);

CREATE INDEX ix_users_default_gear_virtual_ride_gear_id ON public.users_default_gear USING btree (virtual_ride_gear_id);

CREATE INDEX ix_users_default_gear_virtual_run_gear_id ON public.users_default_gear USING btree (virtual_run_gear_id);

CREATE INDEX ix_users_default_gear_walk_gear_id ON public.users_default_gear USING btree (walk_gear_id);

CREATE INDEX ix_users_default_gear_windsurf_gear_id ON public.users_default_gear USING btree (windsurf_gear_id);

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);

CREATE INDEX ix_users_goals_user_id ON public.users_goals USING btree (user_id);

CREATE INDEX ix_users_identity_providers_id ON public.users_identity_providers USING btree (id);

CREATE INDEX ix_users_identity_providers_idp_id ON public.users_identity_providers USING btree (idp_id);

CREATE INDEX ix_users_identity_providers_user_id ON public.users_identity_providers USING btree (user_id);

CREATE UNIQUE INDEX ix_users_integrations_user_id ON public.users_integrations USING btree (user_id);

CREATE UNIQUE INDEX ix_users_privacy_settings_user_id ON public.users_privacy_settings USING btree (user_id);

CREATE INDEX ix_users_sessions_expires_at ON public.users_sessions USING btree (expires_at);

CREATE INDEX ix_users_sessions_last_activity_at ON public.users_sessions USING btree (last_activity_at);

CREATE INDEX ix_users_sessions_oauth_state_id ON public.users_sessions USING btree (oauth_state_id);

CREATE UNIQUE INDEX ix_users_sessions_token_family_id ON public.users_sessions USING btree (token_family_id);

CREATE INDEX ix_users_sessions_user_id ON public.users_sessions USING btree (user_id);

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);

CREATE UNIQUE INDEX uq_activities_user_dedup_key ON public.activities USING btree (user_id, dedup_key);

CREATE UNIQUE INDEX uq_activity_ingestion_jobs_user_active_bulk_import ON public.activity_ingestion_jobs USING btree (user_id) WHERE (((kind)::text = 'bulk_import'::text) AND (completed_at IS NULL));

CREATE UNIQUE INDEX uq_activity_media_activity_content_hash ON public.activity_media USING btree (activity_id, content_hash);

CREATE UNIQUE INDEX uq_gear_user_nickname ON public.gear USING btree (user_id, lower((nickname)::text));

CREATE UNIQUE INDEX uq_health_fasting_one_in_progress_per_user ON public.health_fasting USING btree (user_id) WHERE ((status)::text = 'in_progress'::text);

CREATE UNIQUE INDEX uq_identity_providers_issuer_url_normalized ON public.identity_providers USING btree (rtrim((issuer_url)::text, '/'::text));

CREATE UNIQUE INDEX uq_mfa_factors_user_totp ON public.mfa_factors USING btree (user_id) WHERE ((type)::text = 'totp'::text);

ALTER TABLE ONLY public.account_security_generations
    ADD CONSTRAINT account_security_generations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activities
    ADD CONSTRAINT activities_gear_id_fkey FOREIGN KEY (gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.activities_streams
    ADD CONSTRAINT activities_streams_activity_id_fkey FOREIGN KEY (activity_id) REFERENCES public.activities(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activities
    ADD CONSTRAINT activities_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activity_deletions
    ADD CONSTRAINT activity_deletions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activity_ingestion_jobs
    ADD CONSTRAINT activity_ingestion_jobs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activity_laps
    ADD CONSTRAINT activity_laps_activity_id_fkey FOREIGN KEY (activity_id) REFERENCES public.activities(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activity_media
    ADD CONSTRAINT activity_media_activity_id_fkey FOREIGN KEY (activity_id) REFERENCES public.activities(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activity_sets
    ADD CONSTRAINT activity_sets_activity_id_fkey FOREIGN KEY (activity_id) REFERENCES public.activities(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.activity_workout_steps
    ADD CONSTRAINT activity_workout_steps_activity_id_fkey FOREIGN KEY (activity_id) REFERENCES public.activities(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.auth_known_devices
    ADD CONSTRAINT auth_known_devices_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.follow_request_declines
    ADD CONSTRAINT follow_request_declines_followee_id_fkey FOREIGN KEY (followee_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.follow_request_declines
    ADD CONSTRAINT follow_request_declines_follower_id_fkey FOREIGN KEY (follower_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.follower_blocks
    ADD CONSTRAINT follower_blocks_blocked_id_fkey FOREIGN KEY (blocked_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.follower_blocks
    ADD CONSTRAINT follower_blocks_blocker_id_fkey FOREIGN KEY (blocker_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.followers
    ADD CONSTRAINT followers_followee_id_fkey FOREIGN KEY (followee_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.followers
    ADD CONSTRAINT followers_follower_id_fkey FOREIGN KEY (follower_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.gear_component_deletions
    ADD CONSTRAINT gear_component_deletions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.gear_components
    ADD CONSTRAINT gear_components_gear_id_fkey FOREIGN KEY (gear_id) REFERENCES public.gear(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.gear_components
    ADD CONSTRAINT gear_components_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.gear_deletions
    ADD CONSTRAINT gear_deletions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.gear
    ADD CONSTRAINT gear_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_fasting
    ADD CONSTRAINT health_fasting_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_poop
    ADD CONSTRAINT health_poop_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_record_deletions
    ADD CONSTRAINT health_record_deletions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_sleep
    ADD CONSTRAINT health_sleep_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_steps
    ADD CONSTRAINT health_steps_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_targets
    ADD CONSTRAINT health_targets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_water
    ADD CONSTRAINT health_water_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.health_weight
    ADD CONSTRAINT health_weight_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.idp_session_tokens
    ADD CONSTRAINT idp_session_tokens_idp_id_fkey FOREIGN KEY (idp_id) REFERENCES public.identity_providers(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.idp_session_tokens
    ADD CONSTRAINT idp_session_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.mfa_backup_codes
    ADD CONSTRAINT mfa_backup_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.mfa_factors
    ADD CONSTRAINT mfa_factors_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.oauth_states
    ADD CONSTRAINT oauth_states_idp_id_fkey FOREIGN KEY (idp_id) REFERENCES public.identity_providers(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.oauth_states
    ADD CONSTRAINT oauth_states_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.rotated_refresh_tokens
    ADD CONSTRAINT rotated_refresh_tokens_token_family_id_fkey FOREIGN KEY (token_family_id) REFERENCES public.users_sessions(token_family_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.sign_up_tokens
    ADD CONSTRAINT sign_up_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_api_keys
    ADD CONSTRAINT users_api_keys_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_alpine_ski_gear_id_fkey FOREIGN KEY (alpine_ski_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_gravel_ride_gear_id_fkey FOREIGN KEY (gravel_ride_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_hike_gear_id_fkey FOREIGN KEY (hike_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_mtb_ride_gear_id_fkey FOREIGN KEY (mtb_ride_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_nordic_ski_gear_id_fkey FOREIGN KEY (nordic_ski_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_ows_gear_id_fkey FOREIGN KEY (ows_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_ride_gear_id_fkey FOREIGN KEY (ride_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_run_gear_id_fkey FOREIGN KEY (run_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_snowboard_gear_id_fkey FOREIGN KEY (snowboard_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_tennis_gear_id_fkey FOREIGN KEY (tennis_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_trail_run_gear_id_fkey FOREIGN KEY (trail_run_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_virtual_ride_gear_id_fkey FOREIGN KEY (virtual_ride_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_virtual_run_gear_id_fkey FOREIGN KEY (virtual_run_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_walk_gear_id_fkey FOREIGN KEY (walk_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_default_gear
    ADD CONSTRAINT users_default_gear_windsurf_gear_id_fkey FOREIGN KEY (windsurf_gear_id) REFERENCES public.gear(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_goals
    ADD CONSTRAINT users_goals_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_identity_providers
    ADD CONSTRAINT users_identity_providers_idp_id_fkey FOREIGN KEY (idp_id) REFERENCES public.identity_providers(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_identity_providers
    ADD CONSTRAINT users_identity_providers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_integrations
    ADD CONSTRAINT users_integrations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_local_credentials
    ADD CONSTRAINT users_local_credentials_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_privacy_settings
    ADD CONSTRAINT users_privacy_settings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users_sessions
    ADD CONSTRAINT users_sessions_oauth_state_id_fkey FOREIGN KEY (oauth_state_id) REFERENCES public.oauth_states(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.users_sessions
    ADD CONSTRAINT users_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

INSERT INTO public.mail_settings (id, host, port, security, username, password, from_address, version) VALUES (1, NULL, 587, 'starttls', NULL, NULL, NULL, 1);
INSERT INTO public.migrations (id, name, description, executed) VALUES (7, 'v0.19.0', 'Backfill pre-computed HR zone_percentages for existing streams', true);
INSERT INTO public.server_settings (id, public_shareable_links, public_shareable_links_user_info, login_photo_set, num_records_per_page, signup_enabled, signup_require_admin_approval, signup_require_email_verification, sso_enabled, local_login_enabled, sso_auto_redirect, tileserver_url, tileserver_attribution, map_background_color, password_length_regular_users, password_length_admin_users, tileserver_api_key, units, currency, tileserver_regenerate_thumbnails_on_change, geocoding_service, geocoding_host, geocoding_use_https, geocoding_rate_limit, geocoding_api_key, session_idle_timeout_enabled, session_idle_timeout_hours, session_absolute_timeout_hours, access_token_expire_minutes, refresh_token_expire_days, read_notification_retention_days, version, api_key_max_lifetime_days, password_breach_check_enabled, signup_sso_enabled, require_mfa) VALUES (1, false, false, false, 25, false, false, false, false, true, false, 'https://tile.openstreetmap.org/{z}/{x}/{y}.png', '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors', '#dddddd', 15, 15, NULL, 'metric', 'euro', false, 'nominatim', NULL, true, 1, NULL, true, 72, 720, 15, 7, 90, 1, 365, false, false, 'off');
