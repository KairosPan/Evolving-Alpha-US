from alpha.harness.errors import HarnessError, ImmutableDoctrineError, InvalidTransitionError


def test_immutable_error_is_harness_error():
    assert issubclass(ImmutableDoctrineError, HarnessError)
    with __import__("pytest").raises(HarnessError):
        raise ImmutableDoctrineError("nope")


def test_invalid_transition_is_harness_error():
    assert issubclass(InvalidTransitionError, HarnessError)
