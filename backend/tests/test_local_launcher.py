import importlib.util
from pathlib import Path


def test_local_launcher_prefers_the_project_node_over_path_node(monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts" / "start_local.py"
    spec = importlib.util.spec_from_file_location("thesis_monitor_start_local", script)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    local_node = Path("/project/work/node-v22.23.5/bin/node")
    monkeypatch.setattr(launcher.shutil, "which", lambda _name: "/system/node")

    def glob_nodes(path, pattern):
        if path == launcher.ROOT / "work" and pattern == "node-v*/bin/node":
            return iter([local_node])
        return iter(())

    monkeypatch.setattr(launcher.Path, "glob", glob_nodes)
    monkeypatch.setattr(
        launcher.subprocess,
        "check_output",
        lambda args, **_kwargs: "v24.22.3" if args[0] == "/system/node" else "v22.23.5",
    )

    assert launcher.node_binary() == str(local_node)
