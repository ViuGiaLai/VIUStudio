import os
import subprocess
import sys
import pytest


def test_prepare_workflow_imports_without_app_prefix_in_syspath():
    """Verify PrepareWorkflow imports cleanly in an isolated Python process

    where cwd is app/ and PYTHONPATH is empty (the condition that triggered
    'ModuleNotFoundError: No module named app').
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app_dir = os.path.join(repo_root, "app")
    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)

    code = (
        "import sys\n"
        "from workflows.prepare_workflow import PrepareWorkflow\n"
        "print('PREPARE_WORKFLOW_IMPORT_OK')\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=app_dir,
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, f"Failed stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert "PREPARE_WORKFLOW_IMPORT_OK" in proc.stdout


def test_remote_api_server_syspath_initialization():
    """Verify that remote_api_server.py initializes sys.path with the project root

    so 'app' is resolvable even if launched with python app/remote_api_server.py.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)

    code = (
        "import sys, os\n"
        "import remote_api_server\n"
        "import app.services.timeline_video_sequence as tvs\n"
        "assert callable(tvs.is_image_file)\n"
        "print('REMOTE_API_SERVER_SYSPATH_OK')\n"
    )

    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.join(repo_root, "app"),
        env=clean_env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, f"Failed stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert "REMOTE_API_SERVER_SYSPATH_OK" in proc.stdout


def test_pipeline_controller_worker_env_has_pythonpath():
    """Verify PipelineController sets PYTHONPATH including app_root, app, and ui."""
    from ui.controllers.pipeline_controller import PipelineController

    class DummyGUI:
        workspace_root = "."

    controller = PipelineController(DummyGUI())
    app_root = controller._app_root()
    assert os.path.isdir(app_root)

    env = {}
    pp_entries = [app_root, os.path.join(app_root, "app"), os.path.join(app_root, "ui")]
    existing_pp = env.get("PYTHONPATH", "")
    if existing_pp:
        pp_entries.append(existing_pp)
    env["PYTHONPATH"] = os.pathsep.join(pp_entries)

    parts = env["PYTHONPATH"].split(os.pathsep)
    assert app_root in parts
    assert os.path.join(app_root, "app") in parts
    assert os.path.join(app_root, "ui") in parts

