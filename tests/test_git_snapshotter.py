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


def test_clear_untracked_preserves_runtime_logs(tmp_path):
    snapshotter = GitSnapshotter(
        tmp_path,
        extra_gitignore=["*.o", "/logs/"],
    )
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    log_file = logs_dir / "run.log"
    log_file.write_text("keep me")
    ignored_file = tmp_path / "build.o"
    ignored_file.write_text("delete me")

    snapshotter.clear_untracked(include_ignored=True)

    assert log_file.read_text() == "keep me"
    assert not ignored_file.exists()
