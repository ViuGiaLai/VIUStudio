import ast
import glob
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'app'))

from runtime_paths import get_python_exe, subprocess_hidden_kwargs, subprocess_text_kwargs


def test_subprocess_hidden_kwargs_windows_flags():
    flags = subprocess_hidden_kwargs()
    if os.name == 'nt':
        assert 'creationflags' in flags
        assert flags['creationflags'] & getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) != 0
        assert 'startupinfo' in flags
        si = flags['startupinfo']
        assert isinstance(si, subprocess.STARTUPINFO)
        assert si.dwFlags & getattr(subprocess, 'STARTF_USESHOWWINDOW', 1) != 0
        assert si.wShowWindow == getattr(subprocess, 'SW_HIDE', 0)
    else:
        assert flags == {}


def test_subprocess_text_kwargs_inherits_hidden_flags():
    text_flags = subprocess_text_kwargs()
    assert text_flags.get('text') is True
    assert text_flags.get('encoding') == 'utf-8'
    if os.name == 'nt':
        assert 'creationflags' in text_flags
        assert 'startupinfo' in text_flags


def test_get_python_exe_prefers_pythonw():
    py_exe = get_python_exe()
    assert os.path.isabs(py_exe)
    assert os.path.exists(py_exe)
    if os.name == 'nt' and not getattr(sys, 'frozen', False):
        candidate_w = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
        if os.path.isfile(candidate_w):
            assert py_exe.lower().endswith('pythonw.exe')


def test_all_codebase_subprocesses_have_hidden_flags():
    missing = []
    for root in ['app', 'ui']:
        search_dir = REPO_ROOT / root
        for fpath in search_dir.glob('**/*.py'):
            try:
                tree = ast.parse(fpath.read_text(encoding='utf-8'), filename=str(fpath))
            except Exception:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                is_sub = False
                sub_name = ''
                if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == 'subprocess':
                    is_sub = True
                    sub_name = fn.attr
                elif isinstance(fn, ast.Name) and fn.id in ('Popen', 'run', 'call', 'check_call', 'check_output'):
                    is_sub = True
                    sub_name = fn.id

                if is_sub and sub_name in ('Popen', 'run', 'call', 'check_call', 'check_output'):
                    kw_names = [k.arg for k in node.keywords if k.arg is not None]
                    has_starred_kw = any(k.arg is None for k in node.keywords)
                    has_flags = 'creationflags' in kw_names or 'startupinfo' in kw_names or has_starred_kw
                    if not has_flags:
                        rel = fpath.relative_to(REPO_ROOT)
                        missing.append(f'{rel}:{node.lineno} {sub_name}')

    assert missing == [], f'Found subprocess calls missing hidden flags:\n' + '\n'.join(missing)
