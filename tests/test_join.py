import pytest

from boddos import join


def test_roundtrip():
    token = join.encode("shared-secret-psk", "http://192.168.1.20:8787")
    decoded = join.decode(token)
    assert decoded == {"psk": "shared-secret-psk", "peer": "http://192.168.1.20:8787"}


def test_token_has_stable_prefix():
    token = join.encode("x", "http://a")
    assert token.startswith("bd1.")


def test_decode_rejects_missing_prefix():
    with pytest.raises(ValueError, match="not a boddos join token"):
        join.decode("not-a-real-token")


def test_decode_rejects_garbage_after_prefix():
    with pytest.raises(ValueError, match="malformed join token"):
        join.decode("bd1.not-valid-base64!!!")


def test_decode_rejects_wrong_shape_payload():
    import base64
    import json
    bad = "bd1." + base64.urlsafe_b64encode(json.dumps({"foo": "bar"}).encode()).rstrip(b"=").decode()
    with pytest.raises(ValueError, match="missing psk/peer"):
        join.decode(bad)


def test_decode_tolerates_surrounding_whitespace():
    token = join.encode("p", "http://h:1")
    decoded = join.decode(f"  {token}\n")
    assert decoded["psk"] == "p"
