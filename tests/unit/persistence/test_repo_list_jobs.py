from repodify.models.domain import JobOptions


def test_list_jobs_newest_first_with_total(repo):
    ids = [repo.create_job(f"https://feed/{i}", JobOptions(episode_ids=["e"])) for i in range(3)]

    jobs, total = repo.list_jobs(limit=2, offset=0)

    assert total == 3
    assert [j.id for j in jobs] == [ids[2], ids[1]]  # newest first, limited to 2


def test_list_jobs_offset(repo):
    ids = [repo.create_job(f"https://feed/{i}", JobOptions(episode_ids=["e"])) for i in range(3)]

    jobs, total = repo.list_jobs(limit=2, offset=2)

    assert total == 3
    assert [j.id for j in jobs] == [ids[0]]
