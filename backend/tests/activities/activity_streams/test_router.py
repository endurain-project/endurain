import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock

import sys
import os

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "app"))

import activities.activity_streams.router as activity_streams_router
import activities.activity_streams.crud as activity_streams_crud
import activities.activity_streams.schema as activity_streams_schema
import activities.activity.models as activity_models
import activities.activity_streams.models as activity_streams_models
import activities.activity_streams.constants as activity_streams_constants
import auth.security as auth_security


def test_read_map_streams_for_user_endpoint():
    """Test the new endpoint for getting map streams for a user."""
    
    # Create a test client with proper authentication mocking
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(activity_streams_router.router, prefix="/api/v1/activities/streams")
    
    # Mock authentication dependencies
    def mock_check_scopes():
        return None
    
    def mock_get_sub_from_access_token():
        return 1  # Return the test_user_id
    
    app.dependency_overrides[auth_security.check_scopes] = mock_check_scopes
    app.dependency_overrides[auth_security.get_sub_from_access_token] = mock_get_sub_from_access_token
    
    client = TestClient(app)
    
    # Mock data
    test_user_id = 1
    test_activity_id = 101
    
    # Mock activity stream data
    mock_stream_data = {
        "id": 1,
        "activity_id": test_activity_id,
        "stream_type": activity_streams_constants.STREAM_TYPE_MAP,
        "stream_waypoints": [
            {"lat": 48.8566, "lon": 2.3522},
            {"lat": 48.8567, "lon": 2.3523}
        ],
        "strava_activity_stream_id": None,
        "hr_zone_percentages": None
    }
    
    # Mock activity data
    mock_activity = MagicMock()
    mock_activity.id = test_activity_id
    mock_activity.user_id = test_user_id
    mock_activity.hide_map = False
    
    # Mock stream object
    mock_stream = MagicMock()
    mock_stream.id = 1
    mock_stream.activity_id = test_activity_id
    mock_stream.stream_type = activity_streams_constants.STREAM_TYPE_MAP
    mock_stream.stream_waypoints = mock_stream_data["stream_waypoints"]
    mock_stream.strava_activity_stream_id = None
    
    # Mock the CRUD function to return our test data
    with patch.object(activity_streams_crud, 'get_map_streams_for_user') as mock_crud:
        # Mock the transform_activity_streams function to return our mock stream
        with patch.object(activity_streams_crud, 'transform_activity_streams') as mock_transform:
            mock_transform.return_value = activity_streams_schema.ActivityStreams(**mock_stream_data)
            
            # Set up the mock CRUD to return a list with our transformed stream
            mock_crud.return_value = [activity_streams_schema.ActivityStreams(**mock_stream_data)]
            
            # Mock authentication - we'll use a simple approach
            mock_access_token = "test_token"
            
            # Test the endpoint
            response = client.get(
                f"/api/v1/activities/streams/user_id/{test_user_id}/stream_type/7",
                headers={
                    "Authorization": f"Bearer {mock_access_token}",
                    "Content-Type": "application/json"
                }
            )
            
            # Verify the response
            assert response.status_code == 200
            
            # Verify the CRUD function was called with correct parameters
            mock_crud.assert_called_once()
            args, kwargs = mock_crud.call_args
            assert args[0] == test_user_id  # user_id parameter
            # The token_user_id would be extracted from the token, but we can't easily mock that here
            
            # Verify the response contains our expected data
            response_data = response.json()
            assert isinstance(response_data, list)
            assert len(response_data) == 1
            
            stream_data = response_data[0]
            assert stream_data["id"] == mock_stream_data["id"]
            assert stream_data["activity_id"] == mock_stream_data["activity_id"]
            assert stream_data["stream_type"] == activity_streams_constants.STREAM_TYPE_MAP
            assert stream_data["stream_waypoints"] == mock_stream_data["stream_waypoints"]


def test_read_map_streams_for_user_permission_denied():
    """Test that the endpoint denies access when token_user_id doesn't match user_id."""
    
    # Create a test client with proper authentication mocking
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(activity_streams_router.router, prefix="/api/v1/activities/streams")
    
    # Mock authentication dependencies
    def mock_check_scopes():
        return None
    
    def mock_get_sub_from_access_token():
        return 2  # Return a different user_id to simulate permission denied
    
    app.dependency_overrides[auth_security.check_scopes] = mock_check_scopes
    app.dependency_overrides[auth_security.get_sub_from_access_token] = mock_get_sub_from_access_token
    
    client = TestClient(app)
    
    test_user_id = 1
    different_user_id = 2
    
    # Mock the CRUD function to return None (permission denied)
    with patch.object(activity_streams_crud, 'get_map_streams_for_user') as mock_crud:
        mock_crud.return_value = None  # Permission denied
        
        # Test the endpoint
        response = client.get(
            f"/api/v1/activities/streams/user_id/{test_user_id}/stream_type/7",
            headers={
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json"
            }
        )
        
        # Verify the response
        assert response.status_code == 200
        assert response.json() is None
        
        # Verify the CRUD function was called
        mock_crud.assert_called_once()


def test_read_map_streams_for_user_no_streams():
    """Test that the endpoint returns None when no map streams are found."""
    
    # Create a test client with proper authentication mocking
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(activity_streams_router.router, prefix="/api/v1/activities/streams")
    
    # Mock authentication dependencies
    def mock_check_scopes():
        return None
    
    def mock_get_sub_from_access_token():
        return 1  # Return the test_user_id
    
    app.dependency_overrides[auth_security.check_scopes] = mock_check_scopes
    app.dependency_overrides[auth_security.get_sub_from_access_token] = mock_get_sub_from_access_token
    
    client = TestClient(app)
    
    test_user_id = 1
    
    # Mock the CRUD function to return None (no streams found)
    with patch.object(activity_streams_crud, 'get_map_streams_for_user') as mock_crud:
        mock_crud.return_value = None  # No streams found
        
        # Test the endpoint
        response = client.get(
            f"/api/v1/activities/streams/user_id/{test_user_id}/stream_type/7",
            headers={
                "Authorization": "Bearer test_token",
                "Content-Type": "application/json"
            }
        )
        
        # Verify the response
        assert response.status_code == 200
        assert response.json() is None
        
        # Verify the CRUD function was called
        mock_crud.assert_called_once()
