import pytest
from unittest.mock import MagicMock, patch, ANY
from fastapi import FastAPI, HTTPException, status
import xml.etree.ElementTree as ET

from routes.router import router
from routes.models import Route, RouteImportJob

@pytest.fixture(autouse=True)
def setup_router(fast_api_app: FastAPI):
    try:
        fast_api_app.include_router(router, prefix="/routes")
    except ValueError:
        pass


class TestRoutesAuthorization:

    @pytest.fixture
    def setup_mocks(self, mock_db):
        self.mock_db = mock_db
        # create typical route mock
        self.mock_route = Route(
            id=10,
            user_id=1,
            name="Morning Run",
            description="",
            activity_type="running",
            sub_type="road_running",
            distance=5000.0,
            elevation_gain=50.0,
            route_data={
                "coordinates": [[-1.0, 48.0], [-1.01, 48.01]],
                "coordinates_full": [[-1.0, 48.0], [-1.01, 48.01]]
            }
        )

    def test_get_route_success(self, fast_api_client, setup_mocks):
        self.mock_db.get.return_value = self.mock_route

        # Use mock_token which resolves to mock_user_id = 1 due to conftest overrides
        response = fast_api_client.get("/routes/10", headers={"Authorization": "Bearer mock_token"})
        
        assert response.status_code == 200
        assert response.json()["name"] == "Morning Run"
        self.mock_db.get.assert_called_with(Route, 10)

    def test_get_route_isolation_failure(self, fast_api_client, setup_mocks):
        # assign route to another user
        self.mock_route.user_id = 2 
        self.mock_db.get.return_value = self.mock_route

        response = fast_api_client.get("/routes/10", headers={"Authorization": "Bearer mock_token"})
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Route not found"

    def test_update_route_isolation_failure(self, fast_api_client, setup_mocks):
        self.mock_route.user_id = 2 
        self.mock_db.get.return_value = self.mock_route

        update_data = {
            "name": "Updated Name",
            "activity_type": "cycling",
            "route_data": {"coordinates": [[0,0], [1,1]]}
        }
        
        response = fast_api_client.put("/routes/10", json=update_data, headers={"Authorization": "Bearer mock_token"})
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Route not found"

    def test_delete_route_isolation_failure(self, fast_api_client, setup_mocks):
        self.mock_route.user_id = 2 
        self.mock_db.get.return_value = self.mock_route

        response = fast_api_client.delete("/routes/10", headers={"Authorization": "Bearer mock_token"})
        
        assert response.status_code == 404
        assert response.json()["detail"] == "Route not found"
        self.mock_db.delete.assert_not_called()

    def test_get_routes_list(self, fast_api_client, setup_mocks):
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [self.mock_route]
        self.mock_db.scalars.return_value = mock_scalars

        response = fast_api_client.get("/routes/", headers={"Authorization": "Bearer mock_token"})
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Morning Run"

    def test_create_route(self, fast_api_client, setup_mocks):
        create_data = {
            "name": "New Route",
            "activity_type": "running",
            "route_data": {
                "coordinates": [[-1.0, 48.0], [-1.01, 48.01]]
            }
        }
        
        def mock_add(obj):
            from datetime import datetime
            obj.id = 11
            obj.user_id = 1
            obj.created_at = datetime.utcnow()
            obj.updated_at = datetime.utcnow()
        self.mock_db.add.side_effect = mock_add

        response = fast_api_client.post("/routes/", json=create_data, headers={"Authorization": "Bearer mock_token"})
        
        assert response.status_code == 201
        assert response.json()["name"] == "New Route"
        self.mock_db.add.assert_called_once()
        self.mock_db.commit.assert_called_once()


class TestGPXExport:

    @pytest.fixture
    def setup_mocks(self, mock_db):
        self.mock_db = mock_db
        from datetime import datetime
        self.mock_route = Route(
            id=10,
            user_id=1,
            name="GPX Export Sub",
            description="",
            activity_type="running",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            route_data={
                "coordinates": [[-1.0, 48.0, 100.0], [-1.01, 48.01, 105.0]],
                "coordinates_full": [[-1.0, 48.0, 100.0], [-1.01, 48.01, 105.0]]
            }
        )

    def test_export_route_gpx_success(self, fast_api_client, setup_mocks):
        self.mock_db.get.return_value = self.mock_route
        response = fast_api_client.get("/routes/10/gpx", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/gpx+xml; charset=utf-8"
        assert 'attachment; filename="GPX_Export_Sub.gpx"' in response.headers["content-disposition"]
        
        xml_text = response.text
        assert "<gpx" in xml_text
        assert "GPX Export Sub" in xml_text
        assert 'lat="48.0"' in xml_text
        assert 'lon="-1.0"' in xml_text

    def test_export_route_gpx_no_coordinates(self, fast_api_client, setup_mocks):
        self.mock_route.route_data = {"coordinates_full": []}
        self.mock_db.get.return_value = self.mock_route
        
        response = fast_api_client.get("/routes/10/gpx", headers={"Authorization": "Bearer mock_token"})
        assert response.status_code == 422
        assert response.json()["detail"] == "Route does not contain coordinates to export"


class TestGPXImport:

    def test_import_gpx_empty_file(self, fast_api_client):
        # A truly empty file shouldn't pass the core.file_uploads checks
        response = fast_api_client.post(
            "/routes/import-gpx",
            files={"file": ("test.gpx", b"", "application/gpx+xml")},
            headers={"Authorization": "Bearer mock_token"}
        )
        # Should raise 400 Empty file from file_uploads.py validation
        assert response.status_code == 400

    @patch("routes.router.validate_and_read_gpx_file")
    def test_import_gpx_triggers_job(self, mock_validate, fast_api_client):
        # We mock core.file_uploads validate method to simulate successful read of GPX XML text
        mock_validate.return_value = "<gpx><trk><trkseg><trkpt lat=\"0\" lon=\"0\"></trkpt></trkseg></trk></gpx>"
        
        with patch("routes.router._run_route_gpx_import_job") as mock_job:
            response = fast_api_client.post(
                "/routes/import-gpx",
                files={"file": ("test.gpx", b"<gpx></gpx>", "application/gpx+xml")},
                headers={"Authorization": "Bearer mock_token"}
            )
            
            assert response.status_code == 202
            data = response.json()
            assert "job_id" in data
            assert data["status"] == "pending"
            mock_job.assert_called_once()

