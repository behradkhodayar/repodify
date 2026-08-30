from podcast_compactor.models.domain import JobOptions
from podcast_compactor.models.enums import JobStatus, StageName, StageState


def test_create_and_get_job(repo):
    job_id = repo.create_job("https://feed.example.com/x.xml", JobOptions(episode_ids=["a"]))
    job = repo.get_job(job_id)
    assert job.status == JobStatus.QUEUED.value
    assert job.feed_url == "https://feed.example.com/x.xml"


def test_get_missing_job_raises(repo):
    import pytest

    with pytest.raises(KeyError):
        repo.get_job("nope")


def test_stage_lifecycle_and_artifact(repo):
    job_id = repo.create_job("https://feed", JobOptions())

    repo.start_stage(job_id, StageName.DOWNLOAD)
    repo.finish_stage(job_id, StageName.DOWNLOAD, StageState.DONE, detail="2 episodes")
    repo.add_artifact(job_id, kind="output_audio", uri="file:///out.wav")
    repo.set_report(job_id, {"warnings": ["skipped ep 3"]})
    repo.set_status(job_id, JobStatus.COMPLETED)

    job = repo.get_job(job_id)
    assert job.status == JobStatus.COMPLETED.value
    assert job.current_stage == StageName.DOWNLOAD.value
    assert job.finished_at is not None
    assert len(job.stages) == 1
    assert job.stages[0].state == StageState.DONE.value
    assert job.stages[0].detail == "2 episodes"
    assert len(job.artifacts) == 1
    assert job.artifacts[0].kind == "output_audio"
    assert "skipped ep 3" in job.report_json


def test_start_stage_can_set_initial_detail(repo):
    job_id = repo.create_job("https://feed", JobOptions())
    repo.start_stage(job_id, StageName.DOWNLOAD, detail="0/3")
    job = repo.get_job(job_id)
    assert job.stages[0].state == StageState.RUNNING.value
    assert job.stages[0].detail == "0/3"


def test_update_stage_detail_rewrites_running_row(repo):
    job_id = repo.create_job("https://feed", JobOptions())
    repo.start_stage(job_id, StageName.DOWNLOAD)
    repo.update_stage_detail(job_id, StageName.DOWNLOAD, "1/3 · 40%")
    assert repo.get_job(job_id).stages[0].detail == "1/3 · 40%"
    repo.finish_stage(job_id, StageName.DOWNLOAD, StageState.DONE, detail="3/3 downloaded")
    assert repo.get_job(job_id).stages[0].detail == "3/3 downloaded"


def test_update_stage_detail_without_running_row_raises(repo):
    import pytest

    job_id = repo.create_job("https://feed", JobOptions())
    with pytest.raises(KeyError):
        repo.update_stage_detail(job_id, StageName.DOWNLOAD, "nope")

