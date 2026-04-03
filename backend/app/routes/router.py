from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
import re
import xml.etree.ElementTree as ET
from datetime import datetime
import asyncio
import httpx
from pydantic import BaseModel
from uuid import uuid4
from math import atan2, cos, radians, sin, sqrt
from collections import OrderedDict

from core.database import SessionLocal, get_db
import core.logger as core_logger
from core.file_uploads import validate_and_read_gpx_file
import auth.security as auth_security
from routes.models import Route, RouteImportJob
from routes.schemas import RouteCreate, RouteUpdate, RouteResponse, RouteSearchSuggestionResponse

router = APIRouter()
GEOCODE_CACHE: OrderedDict[str, str] = OrderedDict()
MAX_GEOCODE_CACHE_SIZE = 1000

MAX_GPX_IMPORT_SIZE_BYTES = 10 * 1024 * 1024
MAX_GPX_IMPORT_POINTS = 250000
ROUTE_IMPORT_JOB_TTL_SECONDS = 3600
MIN_EDIT_WAYPOINTS = 25
MAX_EDIT_WAYPOINTS = 120
MAX_EDITOR_COORDINATES = 2500
MAX_LIST_PREVIEW_COORDINATES = 350


class ReverseGeocodePoint(BaseModel):
    """Represents a reverse geocode request point."""

    key: str
    lat: float
    lon: float


class ReverseGeocodeBatchRequest(BaseModel):
    """Represents a batch of reverse geocode points."""

    points: list[ReverseGeocodePoint]


class ReverseGeocodeResult(BaseModel):
    """Represents a reverse geocode result."""

    key: str
    city: str


class ReverseGeocodeBatchResponse(BaseModel):
    """Represents reverse geocode results for a point batch."""

    results: list[ReverseGeocodeResult]


class RouteImportStartResponse(BaseModel):
    """Represents a newly scheduled GPX import job."""

    job_id: str
    status: str


class RouteImportStatusResponse(BaseModel):
    """Represents current status of a GPX import job."""

    job_id: str
    status: str
    route_id: int | None = None
    error: str | None = None


def _haversine_distance_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Computes great-circle distance between two points in meters."""

    radius = 6371000.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return radius * (2 * atan2(sqrt(a), sqrt(1 - a)))


def _validate_and_clean_coordinates(coordinates: list) -> list[list[float]]:
    """Validates GPX coordinates and keeps [lon, lat, ele?] tuples."""

    cleaned: list[list[float]] = []
    for point in coordinates:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue

        try:
            lon = float(point[0])
            lat = float(point[1])
        except (TypeError, ValueError):
            continue

        if lon < -180 or lon > 180 or lat < -90 or lat > 90:
            continue

        entry = [lon, lat]
        if len(point) >= 3 and point[2] is not None:
            try:
                entry.append(float(point[2]))
            except (TypeError, ValueError):
                pass

        cleaned.append(entry)

    if len(cleaned) > MAX_GPX_IMPORT_POINTS:
        raise HTTPException(
            status_code=422,
            detail="GPX contains too many points",
        )

    if len(cleaned) < 2:
        raise HTTPException(
            status_code=422,
            detail="GPX file has insufficient valid points",
        )

    return cleaned


def _project_xy_m(
    lon: float,
    lat: float,
    ref_lat_rad: float,
) -> tuple[float, float]:
    """Projects lon/lat into approximate meter coordinates."""

    radius = 6371000.0
    x = radians(lon) * radius * cos(ref_lat_rad)
    y = radians(lat) * radius
    return x, y


def _distance_point_to_segment_m(
    point: list[float],
    start: list[float],
    end: list[float],
    ref_lat_rad: float,
) -> float:
    """Computes point-to-segment distance in meters."""

    px, py = _project_xy_m(point[0], point[1], ref_lat_rad)
    ax, ay = _project_xy_m(start[0], start[1], ref_lat_rad)
    bx, by = _project_xy_m(end[0], end[1], ref_lat_rad)

    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 0:
        return sqrt((px - ax) ** 2 + (py - ay) ** 2)

    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    cx = ax + t * dx
    cy = ay + t * dy
    return sqrt((px - cx) ** 2 + (py - cy) ** 2)


def _rdp_simplify(
    coordinates: list[list[float]],
    tolerance_m: float,
) -> list[list[float]]:
    """Simplifies coordinates using an iterative RDP algorithm."""

    if len(coordinates) <= 2:
        return coordinates

    ref_lat = sum(point[1] for point in coordinates) / len(coordinates)
    ref_lat_rad = radians(ref_lat)

    keep = [False] * len(coordinates)
    keep[0] = True
    keep[-1] = True

    stack: list[tuple[int, int]] = [(0, len(coordinates) - 1)]
    while stack:
        start_idx, end_idx = stack.pop()
        start = coordinates[start_idx]
        end = coordinates[end_idx]

        max_dist = -1.0
        split_idx = -1
        for i in range(start_idx + 1, end_idx):
            dist = _distance_point_to_segment_m(
                coordinates[i],
                start,
                end,
                ref_lat_rad,
            )
            if dist > max_dist:
                max_dist = dist
                split_idx = i

        if max_dist > tolerance_m and split_idx != -1:
            keep[split_idx] = True
            stack.append((start_idx, split_idx))
            stack.append((split_idx, end_idx))

    return [point for idx, point in enumerate(coordinates) if keep[idx]]


def _limit_points_evenly(
    coordinates: list[list[float]],
    max_points: int,
) -> list[list[float]]:
    """Caps point count while preserving first/last points."""

    if len(coordinates) <= max_points:
        return coordinates

    step = (len(coordinates) - 1) / (max_points - 1)
    indices = [round(i * step) for i in range(max_points)]
    unique_indices = sorted(set(indices))

    if unique_indices[0] != 0:
        unique_indices.insert(0, 0)
    if unique_indices[-1] != len(coordinates) - 1:
        unique_indices.append(len(coordinates) - 1)

    return [coordinates[i] for i in unique_indices]


def _optimize_coordinates(
    coordinates: list[list[float]],
    max_points: int,
    tolerance_m: float,
) -> list[list[float]]:
    """Simplifies then caps coordinates for fast API/UI rendering."""

    simplified = _rdp_simplify(coordinates, tolerance_m=tolerance_m)
    return _limit_points_evenly(simplified, max_points=max_points)


def _compute_distance_and_elevation(coordinates: list[list[float]]) -> tuple[int, int]:
    """Computes total distance and positive elevation gain."""

    total_distance = 0.0
    elevation_gain = 0.0

    for index in range(1, len(coordinates)):
        prev = coordinates[index - 1]
        curr = coordinates[index]
        total_distance += _haversine_distance_m(prev[1], prev[0], curr[1], curr[0])

        if len(prev) >= 3 and len(curr) >= 3:
            delta = curr[2] - prev[2]
            if delta > 0:
                elevation_gain += delta

    return round(total_distance), round(elevation_gain)


def _build_waypoints_from_coordinates(
    coordinates: list[list[float]],
) -> list[dict]:
    """Builds editable waypoints and segment geometries from trace points."""

    target_from_density = round(len(coordinates) / 30)
    target_count = min(
        len(coordinates),
        max(MIN_EDIT_WAYPOINTS, min(MAX_EDIT_WAYPOINTS, target_from_density)),
    )
    step = (len(coordinates) - 1) / (target_count - 1)
    indices = sorted({round(i * step) for i in range(target_count)})

    waypoints: list[dict] = []
    for index, coord_idx in enumerate(indices):
        lon = coordinates[coord_idx][0]
        lat = coordinates[coord_idx][1]
        ele = coordinates[coord_idx][2] if len(coordinates[coord_idx]) >= 3 else None

        waypoint: dict = {
            "lat": lat,
            "lng": lon,
            "ele": ele,
            "mode": "auto",
        }

        if index > 0:
            prev_idx = indices[index - 1]
            segment = coordinates[prev_idx : coord_idx + 1]
            segment_geometry = [[point[0], point[1]] for point in segment]
            segment_distance = 0.0
            for seg_idx in range(1, len(segment_geometry)):
                prev = segment_geometry[seg_idx - 1]
                curr = segment_geometry[seg_idx]
                segment_distance += _haversine_distance_m(
                    prev[1],
                    prev[0],
                    curr[1],
                    curr[0],
                )

            waypoint["segmentGeometry"] = segment_geometry
            waypoint["segmentDistance"] = segment_distance

        waypoints.append(waypoint)

    return waypoints


def _extract_gpx_name(root: ET.Element, filename: str) -> str:
    """Extracts route name from metadata/trk/rte or falls back to filename."""

    for path in (
        ".//{*}metadata/{*}name",
        ".//{*}trk/{*}name",
        ".//{*}rte/{*}name",
        ".//name",
    ):
        name_el = root.find(path)
        if name_el is not None and name_el.text and name_el.text.strip():
            return name_el.text.strip()

    fallback_name = filename.rsplit(".", 1)[0].strip()
    return fallback_name or "Parcours importe"


def _parse_gpx_document(xml_text: str, filename: str) -> tuple[str, list[list[float]]]:
    """Parses GPX XML and extracts route coordinates."""

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as err:
        raise HTTPException(status_code=422, detail="Invalid GPX XML") from err

    points = root.findall(".//{*}trkseg/{*}trkpt")
    if not points:
        points = root.findall(".//{*}rte/{*}rtept")

    coordinates: list[list[float | None]] = []
    for point in points:
        lat = point.attrib.get("lat")
        lon = point.attrib.get("lon")
        ele_el = point.find("{*}ele")
        ele = ele_el.text if ele_el is not None else None
        coordinates.append([lon, lat, ele])

    cleaned = _validate_and_clean_coordinates(coordinates)
    name = _extract_gpx_name(root, filename)
    return name, cleaned


def _build_route_response(
    route: Route,
    for_list_preview: bool = False,
    include_full_coordinates: bool = False,
) -> RouteResponse:
    """Builds API response without exposing full coordinate payloads."""

    route_data = dict(route.route_data or {})
    full_coordinates = route_data.pop("coordinates_full", None)

    if include_full_coordinates and isinstance(full_coordinates, list):
        try:
            route_data["coordinates"] = _validate_and_clean_coordinates(
                full_coordinates,
            )
        except HTTPException:
            pass

    coordinates = route_data.get("coordinates")
    if for_list_preview and isinstance(coordinates, list):
        try:
            cleaned_coordinates = _validate_and_clean_coordinates(coordinates)
        except HTTPException:
            cleaned_coordinates = []

        if len(cleaned_coordinates) >= 2:
            route_data["coordinates"] = _optimize_coordinates(
                cleaned_coordinates,
                max_points=MAX_LIST_PREVIEW_COORDINATES,
                tolerance_m=12.0,
            )
        else:
            route_data["coordinates"] = []

    return RouteResponse(
        id=route.id,
        user_id=route.user_id,
        name=route.name,
        description=route.description,
        activity_type=route.activity_type,
        sub_type=route.sub_type,
        distance=route.distance,
        elevation_gain=route.elevation_gain,
        route_data=route_data,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def _normalize_route_data_for_storage(route_data: dict) -> dict:
    """Normalizes and persists both precise and app coordinates."""

    route_data_safe = dict(route_data or {})
    coordinates = route_data_safe.get("coordinates")

    if not isinstance(coordinates, list):
        raise HTTPException(
            status_code=422,
            detail="Route must include coordinates",
        )

    cleaned_coordinates = _validate_and_clean_coordinates(coordinates)
    route_data_safe["coordinates"] = cleaned_coordinates

    full_coordinates = route_data_safe.get("coordinates_full")
    if isinstance(full_coordinates, list):
        try:
            cleaned_full_coordinates = _validate_and_clean_coordinates(
                full_coordinates,
            )
        except HTTPException:
            cleaned_full_coordinates = cleaned_coordinates
    else:
        cleaned_full_coordinates = cleaned_coordinates

    route_data_safe["coordinates_full"] = cleaned_full_coordinates
    return route_data_safe


def _set_route_import_job_sync(db: Session, job_id: str, payload: dict) -> None:
    job = db.query(RouteImportJob).filter(RouteImportJob.job_id == job_id).first()
    if not job:
        job = RouteImportJob(job_id=job_id)
        db.add(job)
    
    if "status" in payload:
        job.status = payload["status"]
    if "user_id" in payload:
        job.user_id = payload["user_id"]
    if "route_id" in payload:
        job.route_id = payload["route_id"]
    if "error" in payload:
        job.error = payload["error"]
        
    db.commit()


async def _set_route_import_job(
    job_id: str,
    payload: dict,
) -> None:
    """Stores GPX import job state in the database."""
    def _update_db():
        db = SessionLocal()
        try:
            _set_route_import_job_sync(db, job_id, payload)
            
            # Clean up old jobs (older than ROUTE_IMPORT_JOB_TTL_SECONDS)
            cutoff_time = datetime.utcnow().timestamp() - ROUTE_IMPORT_JOB_TTL_SECONDS
            cutoff_dt = datetime.utcfromtimestamp(cutoff_time)
            
            # Use raw filter for old jobs
            db.query(RouteImportJob).filter(
                RouteImportJob.updated_at < cutoff_dt
            ).delete()
            db.commit()
        finally:
            db.close()
            
    await asyncio.to_thread(_update_db)


async def _run_route_gpx_import_job(
    job_id: str,
    user_id: int,
    filename: str,
    xml_text: str,
) -> None:
    """Processes one GPX import job and creates the route."""

    await _set_route_import_job(
        job_id,
        {
            "status": "processing",
            "user_id": user_id,
            "route_id": None,
            "error": None,
        },
    )

    def _sync_parse_and_save() -> int:
        db = SessionLocal()
        try:
            route_name, full_coordinates = _parse_gpx_document(xml_text, filename)
            optimized_coordinates = _optimize_coordinates(
                full_coordinates,
                max_points=MAX_EDITOR_COORDINATES,
                tolerance_m=4.0,
            )
            distance, elevation_gain = _compute_distance_and_elevation(full_coordinates)
            waypoints = _build_waypoints_from_coordinates(optimized_coordinates)

            route = Route(
                user_id=user_id,
                name=route_name,
                description="",
                activity_type="other",
                sub_type=None,
                distance=float(distance),
                elevation_gain=float(elevation_gain),
                route_data={
                    "waypoints": waypoints,
                    "coordinates": optimized_coordinates,
                    "coordinates_full": full_coordinates,
                },
            )
            db.add(route)
            db.commit()
            db.refresh(route)
            return route.id
        finally:
            db.close()

    try:
        route_id = await asyncio.to_thread(_sync_parse_and_save)

        await _set_route_import_job(
            job_id,
            {
                "status": "completed",
                "user_id": user_id,
                "route_id": route_id,
                "error": None,
            },
        )
    except HTTPException as err:
        await _set_route_import_job(
            job_id,
            {
                "status": "failed",
                "user_id": user_id,
                "route_id": None,
                "error": str(err.detail),
            },
        )
    except Exception as err:
        core_logger.print_to_log_and_console(
            f"Unexpected error during GPX import job {job_id}: {err}",
            "error",
            exc=err,
        )
        await _set_route_import_job(
            job_id,
            {
                "status": "failed",
                "user_id": user_id,
                "route_id": None,
                "error": "An unexpected error occurred while processing the GPX file.",
            },
        )


def _build_safe_gpx_filename(route_name: str) -> str:
    """
    Build a filesystem-safe GPX filename.

    Args:
        route_name: Human-readable route name.

    Returns:
        Sanitized GPX filename.

    Raises:
        None.
    """
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", route_name).strip("_")
    return f"{(normalized or 'route').lower()}.gpx"


def _build_geocode_cache_key(lat: float, lon: float) -> str:
    """Builds a stable cache key for geocoding coordinates."""

    return f"{round(lat, 4)}:{round(lon, 4)}"


def _extract_city_label(address: dict) -> str:
    """Extracts best city label from Nominatim address object."""

    return (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
        or address.get("state")
        or address.get("country")
        or ""
    )


async def _reverse_geocode_city(lat: float, lon: float) -> str:
    """Resolves nearest city from coordinates via Nominatim (server-side, no CORS)."""

    cache_key = _build_geocode_cache_key(lat, lon)
    if cache_key in GEOCODE_CACHE:
        GEOCODE_CACHE.move_to_end(cache_key)
        return GEOCODE_CACHE[cache_key]

    city = ""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "format": "json",
                    "lat": f"{lat:.6f}",
                    "lon": f"{lon:.6f}",
                    "zoom": "10",
                    "addressdetails": "1",
                },
                headers={"User-Agent": "Endurain/1.0 (self-hosted fitness tracker)"},
            )
            response.raise_for_status()
            data = response.json()
            city = _extract_city_label(data.get("address", {}))
    except Exception:
        city = ""

    if not city:
        city = f"{lat:.3f}, {lon:.3f}"

    GEOCODE_CACHE[cache_key] = city
    if len(GEOCODE_CACHE) > MAX_GEOCODE_CACHE_SIZE:
        GEOCODE_CACHE.popitem(last=False)
    return city


@router.post(
    "/reverse-geocode-batch",
    response_model=ReverseGeocodeBatchResponse,
)
async def reverse_geocode_batch(
    payload: ReverseGeocodeBatchRequest,
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
):
    """
    Resolve nearest city names for a batch of coordinates.

    Args:
        payload: Batch of coordinates to reverse geocode.
        token_user_id: Authenticated user id.

    Returns:
        Reverse geocoding results indexed by input key.

    Raises:
        HTTPException: If too many points are requested.
    """
    _ = token_user_id
    if len(payload.points) > 120:
        raise HTTPException(
            status_code=422,
            detail="Too many points for reverse geocode batch",
        )

    results: list[ReverseGeocodeResult] = []
    uncached_count = 0
    for point in payload.points:
        cache_key = _build_geocode_cache_key(point.lat, point.lon)
        if cache_key in GEOCODE_CACHE:
            city = GEOCODE_CACHE[cache_key]
            GEOCODE_CACHE.move_to_end(cache_key)
        else:
            if uncached_count >= 15:
                # Prevent HTTP timeouts (max ~16s of Nominatim sleep)
                city = f"{point.lat:.3f}, {point.lon:.3f}"
            else:
                if uncached_count > 0:
                    await asyncio.sleep(1.1)
                city = await _reverse_geocode_city(point.lat, point.lon)
                uncached_count += 1
                
        results.append(ReverseGeocodeResult(key=point.key, city=city))

    return ReverseGeocodeBatchResponse(results=results)

@router.post("/", response_model=RouteResponse, status_code=status.HTTP_201_CREATED)
async def create_route(
    route: RouteCreate,
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
    db: Session = Depends(get_db),
):
    """
    Create a new route.
    """
    normalized_route_data = _normalize_route_data_for_storage(route.route_data)
    new_route = Route(
        user_id=token_user_id,
        name=route.name,
        description=route.description,
        activity_type=route.activity_type,
        sub_type=route.sub_type,
        distance=route.distance,
        elevation_gain=route.elevation_gain,
        route_data=normalized_route_data,
    )
    db.add(new_route)
    db.commit()
    db.refresh(new_route)
    return _build_route_response(new_route)


@router.post(
    "/import-gpx",
    response_model=RouteImportStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_route_from_gpx(
    file: UploadFile = File(...),
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
):
    """Schedules a GPX route import job processed in background."""

    xml_text = await validate_and_read_gpx_file(file, max_size_bytes=MAX_GPX_IMPORT_SIZE_BYTES)
    filename = (file.filename or "").strip()

    job_id = uuid4().hex
    await _set_route_import_job(
        job_id,
        {
            "status": "pending",
            "user_id": token_user_id,
            "route_id": None,
            "error": None,
        },
    )
    asyncio.create_task(
        _run_route_gpx_import_job(
            job_id=job_id,
            user_id=token_user_id,
            filename=filename,
            xml_text=xml_text,
        )
    )

    return RouteImportStartResponse(job_id=job_id, status="pending")


@router.get(
    "/import-gpx/{job_id}",
    response_model=RouteImportStatusResponse,
)
async def get_route_gpx_import_status(
    job_id: str,
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
    db: Session = Depends(get_db),
):
    """Returns current status for a GPX route import job."""

    job = db.query(RouteImportJob).filter(RouteImportJob.job_id == job_id).first()

    if not job or job.user_id != token_user_id:
        raise HTTPException(status_code=404, detail="Import job not found")

    return RouteImportStatusResponse(
        job_id=job.job_id,
        status=job.status,
        route_id=job.route_id,
        error=job.error,
    )

@router.get("/", response_model=List[RouteResponse])
async def get_routes(
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
    db: Session = Depends(get_db),
):
    """
    Get all routes for the current user.
    """
    stmt = select(Route).where(Route.user_id == token_user_id).order_by(Route.created_at.desc())
    routes = db.scalars(stmt).all()
    return [_build_route_response(route, for_list_preview=True) for route in routes]

@router.get("/{route_id}", response_model=RouteResponse)
async def get_route(
    route_id: int,
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
    db: Session = Depends(get_db),
):
    """
    Get a specific route.
    """
    route = db.get(Route, route_id)
    if not route or route.user_id != token_user_id:
        raise HTTPException(status_code=404, detail="Route not found")
    return _build_route_response(route, include_full_coordinates=True)

@router.put("/{route_id}", response_model=RouteResponse)
async def update_route(
    route_id: int,
    route_update: RouteUpdate,
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
    db: Session = Depends(get_db),
):
    """
    Update a route.
    """
    route = db.get(Route, route_id)
    if not route or route.user_id != token_user_id:
        raise HTTPException(status_code=404, detail="Route not found")
    
    update_data = route_update.model_dump(exclude_unset=True)
    if "route_data" in update_data and update_data["route_data"] is not None:
        update_data["route_data"] = _normalize_route_data_for_storage(
            update_data["route_data"],
        )

    for key, value in update_data.items():
        setattr(route, key, value)
        
    db.commit()
    db.refresh(route)
    return _build_route_response(route)

@router.delete("/{route_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_route(
    route_id: int,
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
    db: Session = Depends(get_db),
):
    """
    Delete a route.
    """
    route = db.get(Route, route_id)
    if not route or route.user_id != token_user_id:
        raise HTTPException(status_code=404, detail="Route not found")
    
    db.delete(route)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/{route_id}/gpx", response_class=Response)
async def export_route_gpx(
    route_id: int,
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
    db: Session = Depends(get_db),
):
    """
    Export a route as a GPX file.
    """
    route = db.get(Route, route_id)
    if not route or route.user_id != token_user_id:
        raise HTTPException(status_code=404, detail="Route not found")

    route_data = route.route_data or {}
    coordinates = route_data.get("coordinates_full") or route_data.get("coordinates", [])

    if not coordinates:
        raise HTTPException(
            status_code=422,
            detail="Route does not contain coordinates to export",
        )

    gpx = ET.Element("gpx", {
        "version": "1.1",
        "creator": "Endurain",
        "xmlns": "http://www.topografix.com/GPX/1/1",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xmlns:gpxx": "http://www.garmin.com/xmlschemas/GpxExtensions/v3",
        "xsi:schemaLocation": (
            "http://www.topografix.com/GPX/1/1 "
            "http://www.topografix.com/GPX/1/1/gpx.xsd "
            "http://www.garmin.com/xmlschemas/GpxExtensions/v3 "
            "http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd"
        ),
    })

    metadata = ET.SubElement(gpx, "metadata")
    name_el = ET.SubElement(metadata, "name")
    name_el.text = route.name
    desc_el = ET.SubElement(metadata, "desc")
    
    desc_parts = []
    if route.description:
        desc_parts.append(route.description)
    if route.distance:
        desc_parts.append(f"Distance: {route.distance / 1000:.2f} km")
    if route.elevation_gain is not None:
        desc_parts.append(f"Elevation Gain: {int(route.elevation_gain)} m")
    
    desc_el.text = "\n".join(desc_parts)

    time_el = ET.SubElement(metadata, "time")
    time_el.text = route.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Waypoints as standalone <wpt> markers (no connecting line, not a route)
    for index, point in enumerate(route_data.get("waypoints", []), start=1):
        lat = point.get("lat")
        lon = point.get("lng")
        if lat is None or lon is None:
            continue
        wpt = ET.SubElement(gpx, "wpt", {"lat": str(lat), "lon": str(lon)})
        wpt_name = ET.SubElement(wpt, "name")
        wpt_name.text = f"WP{index:02d}"

    trk = ET.SubElement(gpx, "trk")
    trk_name = ET.SubElement(trk, "name")
    trk_name.text = route.name

    if route.activity_type:
        trk_type = ET.SubElement(trk, "type")
        trk_type.text = route.activity_type

    if route.distance or route.elevation_gain is not None:
        ext_el = ET.SubElement(trk, "extensions")
        gpxx_ext = ET.SubElement(ext_el, "gpxx:TrackExtension")
        if route.distance:
            dist_el = ET.SubElement(gpxx_ext, "gpxx:Distance")
            dist_el.text = f"{route.distance:.1f}"
        if route.elevation_gain is not None:
            asc_el = ET.SubElement(gpxx_ext, "gpxx:Ascent")
            asc_el.text = f"{route.elevation_gain:.1f}"

    trkseg = ET.SubElement(trk, "trkseg")

    for pt in coordinates:
        if len(pt) >= 2:
            lon, lat = pt[0], pt[1]
            trkpt = ET.SubElement(
                trkseg,
                "trkpt",
                {"lat": str(lat), "lon": str(lon)},
            )
            if len(pt) >= 3 and pt[2] is not None:
                ele = ET.SubElement(trkpt, "ele")
                ele.text = str(pt[2])

    gpx_bytes = ET.tostring(
        gpx,
        encoding="utf-8",
        xml_declaration=True,
    )
    filename = _build_safe_gpx_filename(route.name)

    return Response(
        content=gpx_bytes,
        media_type="application/gpx+xml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            )
        },
    )

@router.get("/geocoding/search", response_model=list[RouteSearchSuggestionResponse])
async def search_locations(
    q: str,
    lang: str = "en",
    token_user_id: int = Depends(auth_security.get_sub_from_access_token),
):
    """
    Search for locations using Nominatim API (proxied to avoid client-side CORS/rate limit issues).
    """
    trimmed_query = q.strip()
    if not trimmed_query:
        return []

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "format": "jsonv2",
                    "addressdetails": "1",
                    "limit": "5",
                    "q": trimmed_query,
                    "accept-language": lang,
                },
                headers={
                    "User-Agent": "EndurainApp/1.0"
                },
                timeout=10.0
            )
            response.raise_for_status()
            data = response.json()
            
            suggestions = []
            if isinstance(data, list):
                for item in data[:5]:
                    address = item.get("address", {})
                    
                    main_label = (
                        item.get("name") or 
                        address.get("city") or 
                        address.get("town") or 
                        address.get("village") or 
                        address.get("municipality") or 
                        address.get("road") or 
                        (item.get("display_name", "").split(",")[0] if item.get("display_name") else "Search result")
                    )
                    
                    meta_parts = [
                        address.get("city") or address.get("town") or address.get("village") or address.get("municipality"),
                        address.get("county") or address.get("state_district") or address.get("state"),
                        address.get("country"),
                        address.get("postcode")
                    ]
                    
                    meta_str = " • ".join(filter(None, meta_parts))
                    
                    suggestions.append({
                        "id": str(item.get("place_id", uuid4().hex)),
                        "label": main_label,
                        "meta": meta_str,
                        "lat": float(item.get("lat", 0)),
                        "lon": float(item.get("lon", 0))
                    })
                    
            return suggestions
            
    except Exception as e:
        core_logger.print_to_log_and_console(f"Nominatim search error: {e}", "error")
        return []
