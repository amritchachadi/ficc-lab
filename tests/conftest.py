"""Shared test configuration."""

from hypothesis import HealthCheck, settings

# Deadlines make property tests fail intermittently on a cold or loaded CI
# runner, which is a flapping test rather than a real defect. Budget the
# work with max_examples instead.
settings.register_profile(
    "default",
    deadline=None,
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.register_profile("fast", deadline=None, max_examples=25)
settings.load_profile("default")
