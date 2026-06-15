from alpha.loop.floor_breaker import _mad, _fallback_trip, _MAD_EPS


def test_mad():
    assert _mad([1.0, 1.0, 1.0]) == 0.0
    # median=2; abs devs=[1,0,1]; median of devs = 1
    assert _mad([1.0, 2.0, 3.0]) == 1.0


def test_fallback_trip_via_median_minus_c_mad():
    # history with spread: median & MAD nonzero -> threshold = median - c*MAD
    hist = [0.4, 0.5, 0.6, 0.5, -0.9]            # median=0.5; devs=[.1,0,.1,0,1.4]; MAD=0.1
    trip, rolling, thr, reason = _fallback_trip(hist, k=2, c=2.0, floor_abs=-0.2)
    # rolling=mean(last2)=mean(0.5,-0.9)=-0.2 ; thr=0.5-2*0.1=0.3 ; -0.2 < 0.3 -> trip
    assert trip is True and abs(rolling - (-0.2)) < 1e-9 and abs(thr - 0.3) < 1e-9
    assert "MAD" in reason


def test_fallback_trip_mad_zero_uses_floor_abs():
    hist = [0.3, 0.3, 0.3, -0.5]                  # median=0.3; devs=[0,0,0,0.8]; MAD=0 (<eps)
    trip, rolling, thr, reason = _fallback_trip(hist, k=2, c=2.0, floor_abs=-0.2)
    # MAD~0 -> threshold is floor_abs; rolling=mean(0.3,-0.5)=-0.1 ; -0.1 < -0.2? NO
    assert trip is False and abs(thr - (-0.2)) < 1e-9 and "floor_abs" in reason
    # push rolling below the floor
    trip2, rolling2, _, _ = _fallback_trip([0.3, 0.3, 0.3, -0.9], k=2, c=2.0, floor_abs=-0.2)
    assert trip2 is True and rolling2 < -0.2     # mean(0.3,-0.9)=-0.3 < -0.2


def test_fallback_no_trip_when_healthy():
    trip, _, _, _ = _fallback_trip([0.3, 0.3, 0.3, 0.3], k=3, c=2.0, floor_abs=-0.2)
    assert trip is False and _MAD_EPS == 1e-9
