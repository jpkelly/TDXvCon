"""Models: spec validation, defaults, serialization round-trips."""

from __future__ import annotations

import pytest

from vcon.errors import InputError, OutputError
from vcon.models import Job, JobSpec, JobStatus, _default_output_for


def test_validate_paths_missing_input(sample_spec):
    spec = sample_spec.model_copy() if hasattr(sample_spec, "model_copy") else sample_spec
    spec = JobSpec(
        input=spec.input.with_name("missing.mov"), output=spec.output, codec="notchlc"
    )
    with pytest.raises(InputError, match="not found"):
        spec.validate_paths()


def test_validate_paths_input_is_directory(sample_input, tmp_path):
    spec = JobSpec(input=tmp_path, output=tmp_path / "out.mov")
    with pytest.raises(InputError, match="not a file"):
        spec.validate_paths()


def test_validate_paths_missing_output_dir(sample_input, tmp_path):
    spec = JobSpec(input=sample_input, output=tmp_path / "nope" / "out.mov")
    with pytest.raises(OutputError, match="does not exist"):
        spec.validate_paths()


def test_resolved_quality_fallback_chain():
    spec = JobSpec(input=None, output=None)  # type: ignore[arg-type]
    assert spec.resolved_quality("best") == "best"
    assert spec.resolved_quality(None) == "optimal"


def test_spec_dict_roundtrip(sample_spec):
    d = sample_spec.as_dict()
    clone = JobSpec.from_dict(d)
    assert clone == sample_spec


def test_default_output_naming(sample_input):
    out = _default_output_for(sample_input, "notchlc")
    assert out.name == "clip.notchlc.mov"
    assert out.parent == sample_input.parent


def test_job_lifecycle_flags(sample_spec):
    job = Job(spec=sample_spec, id="j1")
    assert not job.is_terminal
    assert job.percent is None

    job.status = JobStatus.RUNNING
    job.total_frames = 100
    job.progress_frame = 25
    assert job.percent == 25.0
    assert not job.is_terminal

    job.status = JobStatus.DONE
    assert job.is_terminal


def test_job_dict_roundtrip(sample_spec):
    job = Job(spec=sample_spec, id="j9", status="running", total_frames=10)
    d = job.as_dict()
    assert d["id"] == "j9"
    assert d["spec"]["codec"] == "notchlc"
    assert d["status"] == "running"