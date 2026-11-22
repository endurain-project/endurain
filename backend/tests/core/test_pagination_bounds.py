"""The paging parameters bound the page number as well as the page size."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import core.pagination as core_pagination


def _client(dependency) -> TestClient:
    app = FastAPI()

    @app.get("/items")
    def items(page: core_pagination.PageParams = Depends(dependency)) -> dict[str, int]:
        return {"page_number": page.page_number, "num_records": page.num_records}

    return TestClient(app)


@pytest.mark.parametrize("dependency", [core_pagination.list_page_params, core_pagination.child_page_params])
class TestPageNumberBound:
    def test_the_maximum_is_accepted(self, dependency):
        response = _client(dependency).get("/items", params={"page_number": core_pagination.MAX_PAGE_NUMBER})

        assert response.status_code == 200
        assert response.json()["page_number"] == core_pagination.MAX_PAGE_NUMBER

    def test_above_the_maximum_is_refused(self, dependency):
        response = _client(dependency).get("/items", params={"page_number": core_pagination.MAX_PAGE_NUMBER + 1})

        assert response.status_code == 422

    def test_zero_is_refused(self, dependency):
        assert _client(dependency).get("/items", params={"page_number": 0}).status_code == 422
