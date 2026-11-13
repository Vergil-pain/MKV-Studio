from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import core


def test_kind_of_is_case_insensitive() -> None:
    assert core.kind_of("movie.MP4") == "video"
    assert core.kind_of("dub.FLAC") == "audio"
    assert core.kind_of("captions.SRT") == "subtitle"
    assert core.kind_of("readme.txt") is None


def test_guess_language_handles_prefix_and_suffix() -> None:
    assert core.guess_language("movie.fr.srt") == "fre"
    assert core.guess_language("dub_arabic.mka") == "ara"
    assert core.guess_language("fa_movie.srt") == "per"
    assert core.guess_language("movie.unknown.srt") == "und"


def test_progress_parser_uses_microseconds() -> None:
    assert core.parse_progress_line("out_time_us=2500000") == 2.5
    assert core.parse_progress_line("out_time_ms=1250000") == 1.25
    assert core.parse_progress_line("progress=end") is None
    assert core.parse_progress_line("out_time_us=bad") is None


def test_validate_job_prevents_overwriting_video_or_extra_track(tmp_path: Path) -> None:
    video_path = tmp_path / "source.mp4"
    audio_path = tmp_path / "dub.wav"
    video_path.write_bytes(b"video")
    audio_path.write_bytes(b"audio")
    video = core.ProbeResult(str(video_path), 1.0, "mov,mp4", [
        core.StreamInfo(0, "video", "h264"),
    ])

    overwrite_video = core.Job(video, [], str(video_path))
    assert any("source video" in message for message in core.validate_job(overwrite_video))

    overwrite_audio = core.Job(video, [core.ExtraTrack("audio", str(audio_path))], str(audio_path))
    assert any("added track" in message for message in core.validate_job(overwrite_audio))


def test_build_command_maps_source_and_extra_tracks(tmp_path: Path) -> None:
    video = core.ProbeResult("source.mp4", 10.0, "mov,mp4", [
        core.StreamInfo(0, "video", "h264"),
        core.StreamInfo(1, "audio", "aac"),
    ])
    job = core.Job(
        video=video,
        extras=[
            core.ExtraTrack("audio", "dub.wav", language="per", delay_ms=250, default=True),
            core.ExtraTrack("subtitle", "captions.vtt", language="eng", title="English", default=True),
        ],
        output=str(tmp_path / "result.mkv"),
    )
    cmd = core.build_command("ffmpeg", job)
    assert ["-itsoffset", "0.250"] == cmd[cmd.index("-itsoffset"):cmd.index("-itsoffset") + 2]
    assert "-map" in cmd and "0:0" in cmd and "0:1" in cmd and "1:a:0" in cmd and "2:s:0" in cmd
    assert "-c:s:0" in cmd and "srt" in cmd
    assert "language=per" in cmd and "title=English" in cmd
    assert cmd[-1].endswith("result.mkv")


def test_ffmpeg_remux_integration(tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg and FFprobe are required for this integration test")

    source = tmp_path / "source.mp4"
    extra_audio = tmp_path / "dub.wav"
    subtitles = tmp_path / "captions.srt"
    output = tmp_path / "result.mkv"

    subprocess.run([
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "1",
        "-c:v", "mpeg4", "-c:a", "aac", str(source),
    ], check=True, capture_output=True)
    subprocess.run([
        ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=44100",
        "-t", "1", str(extra_audio),
    ], check=True, capture_output=True)
    subtitles.write_text("1\n00:00:00,000 --> 00:00:00,800\nTest subtitle\n", encoding="utf-8")

    probe = core.probe(ffprobe, str(source))
    job = core.Job(
        video=probe,
        extras=[
            core.ExtraTrack("audio", str(extra_audio), language="eng", title="Dub"),
            core.ExtraTrack("subtitle", str(subtitles), language="eng", title="Captions", default=True),
        ],
        output=str(output),
    )
    assert core.validate_job(job) == []
    command = core.build_command(ffmpeg, job)
    subprocess.run(command, check=True, capture_output=True)

    result = core.probe(ffprobe, str(output))
    assert len(result.of_kind("video")) == 1
    assert len(result.of_kind("audio")) == 2
    assert len(result.of_kind("subtitle")) == 1
    assert output.is_file() and output.stat().st_size > 0
