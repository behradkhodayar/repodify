from repodify.models.domain import JobOptions, Speaker, VoiceAssignment
from repodify.summarize.guidance import runtime_guidance


def test_guidance_smart_length_and_single_narrator():
    text = runtime_guidance(
        JobOptions(length_mode="smart", target_minutes=None),
        [],
    )
    assert "natural" in text.lower()
    assert "single narrator" in text.lower()


def test_guidance_manual_length_and_original_voices():
    text = runtime_guidance(
        JobOptions(
            length_mode="manual",
            target_minutes=25,
            assign_voices=True,
            use_original_voices=True,
            clone=True,
            preserve_speakers=True,
        ),
        [Speaker(id="SPEAKER_00", speaking_seconds=12.0, gender="male")],
    )
    assert "25" in text
    assert "original" in text.lower() or "cloned" in text.lower()
    assert "SPEAKER_00" in text
    assert "male" in text


def test_guidance_stock_replacements():
    text = runtime_guidance(
        JobOptions(
            assign_voices=True,
            use_original_voices=False,
            preserve_speakers=True,
            voice_assignments=[
                VoiceAssignment(speaker_id="SPEAKER_00", mode="stock", stock_voice="am_adam"),
            ],
        ),
        [Speaker(id="SPEAKER_00", gender="male")],
    )
    assert "am_adam" in text or "Adam" in text or "stock" in text.lower()
