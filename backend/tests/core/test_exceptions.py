class TestAccessConcealedError:
    def test_is_indistinguishable_from_not_found_to_a_client(self):
        import core.exceptions as core_exceptions

        concealed = core_exceptions.AccessConcealedError()
        missing = core_exceptions.NotFoundError()

        assert (concealed.status_code, concealed.code, concealed.title, concealed.detail) == (
            missing.status_code,
            missing.code,
            missing.title,
            missing.detail,
        )
        assert isinstance(concealed, core_exceptions.NotFoundError)


class TestDependencyFailedError:
    def test_renders_as_a_424_failed_dependency(self):
        import core.exceptions as core_exceptions

        error = core_exceptions.DependencyFailedError("Strava rejected the code")

        assert (error.status_code, error.code, error.title, error.detail) == (
            424,
            "dependency-failed",
            "Failed Dependency",
            "Strava rejected the code",
        )
