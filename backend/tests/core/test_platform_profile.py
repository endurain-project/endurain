"""Tests for core.platform.profile."""

import pytest

import core.platform.profile as platform_profile


class TestParseProfile:
    """Tests for parse_profile()."""

    def test_none_defaults_to_local(self):
        assert platform_profile.parse_profile(None) is platform_profile.DeploymentProfile.LOCAL

    def test_empty_and_whitespace_default_to_local(self):
        assert platform_profile.parse_profile("") is platform_profile.DeploymentProfile.LOCAL
        assert platform_profile.parse_profile("   ") is platform_profile.DeploymentProfile.LOCAL

    def test_case_and_whitespace_insensitive(self):
        assert platform_profile.parse_profile(" Distributed ") is platform_profile.DeploymentProfile.DISTRIBUTED
        assert platform_profile.parse_profile("LOCAL") is platform_profile.DeploymentProfile.LOCAL
        assert platform_profile.parse_profile("custom") is platform_profile.DeploymentProfile.CUSTOM

    def test_existing_profile_passthrough(self):
        assert (
            platform_profile.parse_profile(platform_profile.DeploymentProfile.DISTRIBUTED)
            is platform_profile.DeploymentProfile.DISTRIBUTED
        )

    def test_invalid_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid DEPLOYMENT_PROFILE"):
            platform_profile.parse_profile("distributd")


class TestClassifyStateUri:
    """Tests for classify_state_uri()."""

    @pytest.mark.parametrize(
        ("uri", "expected"),
        [
            ("memory://", platform_profile.StateBackendKind.MEMORY),
            ("MEMORY://", platform_profile.StateBackendKind.MEMORY),
            ("  memory://  ", platform_profile.StateBackendKind.MEMORY),
            ("redis://localhost:6379/0", platform_profile.StateBackendKind.REDIS),
            ("rediss://host:6380/1", platform_profile.StateBackendKind.REDIS),
            ("unix:///var/run/redis.sock", platform_profile.StateBackendKind.REDIS),
            ("postgres://x", platform_profile.StateBackendKind.UNKNOWN),
            ("", platform_profile.StateBackendKind.UNKNOWN),
            (None, platform_profile.StateBackendKind.UNKNOWN),
        ],
    )
    def test_classification(self, uri, expected):
        assert platform_profile.classify_state_uri(uri) is expected


class TestDeploymentTopology:
    """Tests for DeploymentTopology.requires_shared_state and resolve_topology()."""

    @pytest.mark.parametrize(
        ("profile", "workers", "expected"),
        [
            (platform_profile.DeploymentProfile.LOCAL, 1, False),
            (platform_profile.DeploymentProfile.LOCAL, 2, True),
            (platform_profile.DeploymentProfile.DISTRIBUTED, 1, True),
            (platform_profile.DeploymentProfile.DISTRIBUTED, 4, True),
            (platform_profile.DeploymentProfile.CUSTOM, 1, False),
            (platform_profile.DeploymentProfile.CUSTOM, 3, True),
        ],
    )
    def test_requires_shared_state(self, profile, workers, expected):
        topology = platform_profile.resolve_topology(profile, workers)
        assert topology.requires_shared_state is expected

    @pytest.mark.parametrize(
        ("workers", "expected"),
        [(0, 1), (-5, 1), (1, 1), (8, 8)],
    )
    def test_web_workers_clamped_to_at_least_one(self, workers, expected):
        topology = platform_profile.resolve_topology(platform_profile.DeploymentProfile.LOCAL, workers)
        assert topology.web_workers == expected
