from youzi.harness.errors import ImmutableDoctrineError, InvalidTransitionError


def test_error_types_are_distinct_runtime_errors():
    assert issubclass(ImmutableDoctrineError, RuntimeError)
    assert issubclass(InvalidTransitionError, RuntimeError)
    assert ImmutableDoctrineError is not InvalidTransitionError
