"""Delete this task's tmp folder (progress-record.md, cleanup item 1).

Run from the repo root with the path that passed check_cleanup.py tmp:
    python -I <dev-workflow install root>/assets/progress/delete_tmp.py <path> --task <task code>
The tmp check of check_cleanup.py (same folder) runs again first, in this
process; when it cannot load, cannot finish or does not pass, nothing is
deleted and the exit code is non-zero. The conditions for clearing a
read-only file are in progress-record.md. Python 3.12+, standard library only.
"""

from __future__ import annotations

import functools
import importlib.util
import os
import shutil
import stat
import sys
from pathlib import Path

CHECKER_FILE = "check_cleanup.py"
CHECKER_MODULE = "toukadev_check_cleanup_for_delete"


def clear_readonly_then_unlink(root, func, path, exc):
    """onexc for shutil.rmtree: on Windows, clear the read-only attribute of
    a regular file under root and unlink it; re-raise exc in every other case.
    """
    if sys.platform != "win32" or func is not os.unlink:
        raise exc
    if not isinstance(exc, PermissionError):
        raise exc
    top = os.path.normcase(os.path.abspath(root))
    target = os.path.normcase(os.path.abspath(path))
    try:
        inside = target != top and os.path.commonpath([top, target]) == top
    except ValueError:
        inside = False
    if not inside:
        raise exc
    try:
        info = os.lstat(path)
    except OSError:
        info = None
    if (
        info is None
        or not stat.S_ISREG(info.st_mode)
        or info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        or not info.st_file_attributes & stat.FILE_ATTRIBUTE_READONLY
        or info.st_nlink != 1
    ):
        raise exc
    if os.chmod in os.supports_follow_symlinks:
        os.chmod(path, stat.S_IWRITE, follow_symlinks=False)
    else:
        os.chmod(path, stat.S_IWRITE)
    os.unlink(path)


def checked_root(argument, task):
    """Re-run the tmp check as check_cleanup.main does (find_repo_root(cwd),
    resolve_argument, check_tmp). Return the checked path; return None when
    loading fails, any exception is raised (CheckError included) or the check
    does not pass, so nothing is deleted.
    """
    # No __pycache__ in the Skill install folder.
    sys.dont_write_bytecode = True
    try:
        spec = importlib.util.spec_from_file_location(
            CHECKER_MODULE, Path(__file__).with_name(CHECKER_FILE)
        )
        checker = importlib.util.module_from_spec(spec)
        # @dataclass with postponed annotations looks the module up here.
        sys.modules[CHECKER_MODULE] = checker
        spec.loader.exec_module(checker)
        checker.configure_streams()
        cwd = Path.cwd()
        repo = checker.find_repo_root(cwd)
        target = checker.resolve_argument(argument, cwd)
        verdict = checker.check_tmp(repo, target, task)
    except BaseException as error:
        print(f"Not deleted: the tmp check did not finish: {error!r}", file=sys.stderr)
        return None
    if not verdict.ok:
        print(f"Not deleted: {verdict.target}", file=sys.stderr)
        for reason in verdict.reasons:
            print(f"- {reason}", file=sys.stderr)
        return None
    return str(target)


if __name__ == "__main__":
    if sys.version_info < (3, 12):
        sys.exit("Python 3.12 or newer is required.")
    if len(sys.argv) != 4 or sys.argv[2] != "--task":
        sys.exit("usage: python -I delete_tmp.py <tmp folder> --task <task code>")
    root = checked_root(sys.argv[1], sys.argv[3])
    if root is None:
        sys.exit(1)
    shutil.rmtree(root, onexc=functools.partial(clear_readonly_then_unlink, root))
