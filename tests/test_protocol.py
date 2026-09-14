"""Protocol: encode/decode round-trips, framing, malformed input."""

from __future__ import annotations

import json

import pytest

from vcon.protocol import (
    Cancel,
    Submit,
    decode_msg,
    encode_msg,
    is_hello,
    hello_version,
    make_hello,
)


def test_encode_submit_roundtrip():
    msg = Submit(
        job_id="j1",
        input="/data/clip.mov",
        output="/data/clip.nlc.mov",
        params={"codec": "notchlc", "quality": "optimal"},
    )
    wire = encode_msg(msg)
    assert wire.endswith(b"\n")
    parsed = decode_msg(wire)
    assert parsed["type"] == "submit"
    assert parsed["id"] == "j1"
    assert parsed["params"]["codec"] == "notchlc"


def test_encode_cancel_roundtrip():
    wire = encode_msg(Cancel(job_id="j2"))
    parsed = decode_msg(wire)
    assert parsed == {"type": "cancel", "id": "j2"}


def test_decode_rejects_non_json():
    with pytest.raises(Exception):
        decode_msg(b"this is not json\n")


def test_decode_rejects_non_object():
    with pytest.raises(Exception):
        decode_msg(json.dumps(["a", "list"]) + "\n")


def test_decode_rejects_missing_type():
    with pytest.raises(Exception, match="not a protocol message"):
        decode_msg(json.dumps({"id": "j1"}) + "\n")


def test_hello_detection():
    hello = make_hello(version=1)
    assert is_hello(hello)
    assert hello_version(hello) == 1
    assert not is_hello({"type": "progress", "id": "j1"})


def test_unicode_paths_survive_the_wire():
    msg = Submit(
        job_id="j3",
        input="/data/émoji ✓ clip.mov",
        output="/data/émoji ✓ clip.nlc.mov",
        params={},
    )
    parsed = decode_msg(encode_msg(msg))
    assert parsed["input"] == "/data/émoji ✓ clip.mov"


def test_params_dict_passes_arbitrary_codec_options():
    msg = Submit(
        job_id="j4", input="a", output="b",
        params={"videocodec": "Hap", "videocodectype": "Hap Q Alpha",
                "moviepixelformat": "RGBA", "moviecontainer": ".mov",
                "free_form_future_option": 42},
    )
    parsed = decode_msg(encode_msg(msg))
    assert parsed["params"]["free_form_future_option"] == 42