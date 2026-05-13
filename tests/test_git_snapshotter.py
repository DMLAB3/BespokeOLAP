from llm_cache.git_snapshotter import GitSnapshotter


def test_is_git_remote_url_accepts_scp_like_ssh_url():
    assert GitSnapshotter._is_git_remote_url(
        "git@github.com:DMLAB3/bespoke_cache.git"
    )


def test_is_git_remote_url_accepts_standard_urls():
    assert GitSnapshotter._is_git_remote_url(
        "https://github.com/DMLAB3/bespoke_cache.git"
    )
    assert GitSnapshotter._is_git_remote_url(
        "ssh://git@github.com/DMLAB3/bespoke_cache.git"
    )


def test_is_git_remote_url_rejects_plain_remote_name():
    assert not GitSnapshotter._is_git_remote_url("cache_repo")
