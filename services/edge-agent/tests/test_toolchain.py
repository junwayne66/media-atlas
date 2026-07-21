import shutil

from videoforge_edge_agent.toolchain import probe_toolchain


def test_probe_reports_both_binaries_structure() -> None:
    result = probe_toolchain()
    assert set(result) == {"ffmpeg", "ffprobe"}
    for name, info in result.items():
        if shutil.which(name) is None:
            assert info is None
        else:
            assert info is not None and info["path"] and info["version"]
