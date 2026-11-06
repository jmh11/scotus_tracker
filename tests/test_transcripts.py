"""Fixed checks for the transcript-link parser."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import parse_transcripts as pt  # noqa: E402

ROW = "<a href='../argument_transcripts/2026/{f}.pdf' Target='_blank'>{t}</a>"


def test_matching_link():
    found, problems = pt.parse(ROW.format(f="25-170_8m58", t="25-170"))
    assert not problems
    assert found == {"25-170": "https://www.supremecourt.gov/oral_arguments/argument_transcripts/2026/25-170_8m58.pdf"}


def test_mismatched_link_is_an_error():
    _, problems = pt.parse(ROW.format(f="25-171_8m58", t="25-170"))
    assert problems


def test_real_page():
    found, problems = pt.parse(pt.PAGE.read_text(encoding="utf-8", errors="replace"))
    assert not problems and len(found) >= 10


AUDIO = "<a href='../audio/2026/{f}'>{t}</a>"


def test_audio_link():
    found, problems = pt.parse_audio(AUDIO.format(f="25-170", t="25-170"))
    assert not problems
    assert found == {"25-170": "https://www.supremecourt.gov/oral_arguments/audio/2026/25-170"}


def test_mismatched_audio_link_is_an_error():
    _, problems = pt.parse_audio(AUDIO.format(f="25-171", t="25-170"))
    assert problems


def test_real_audio_page():
    found, problems = pt.parse_audio(pt.AUDIO_PAGE.read_text(encoding="utf-8", errors="replace"))
    assert not problems and len(found) >= 10
