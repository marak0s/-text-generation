import io
import contextlib
import os
import tempfile
import traceback
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from modules import dataset_tool

# Maintain execution environments per session so variables persist between runs
_session_envs: dict[str, dict] = {}


def execute_python(code: str, out_dir: str | Path | None = None):
    """Execute arbitrary Python code and capture stdout and generated images.

    Returns a dict with 'stdout' and 'images' keys. Images are file paths to
    any matplotlib figures created by the code. If ``out_dir`` is provided,
    images are saved under that directory. Variables defined during execution
    persist for subsequent calls within the same ``out_dir``.
    """
    stdout = io.StringIO()
    images: list[str] = []
    out_path = Path(out_dir).resolve() if out_dir else None
    prev_cwd = None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)
        prev_cwd = os.getcwd()
        os.chdir(out_path)
    # Reuse the same environment for each session directory
    key = str(out_path) if out_path else "__default__"
    env = _session_envs.setdefault(
        key,
        {
            "plt": plt,
            "pd": pd,
            "get_table_path": dataset_tool.get_table_path,
            "load_table": dataset_tool.load_table,
        },
    )
    # Patch pandas readers to forbid direct file access
    if not env.get("_path_patched"):
        def _block(name):
            def inner(*a, **kw):
                raise RuntimeError(f"Запрещено использовать pd.{name}; данные обязательно получайте только через load_table()")
            return inner

        for name in ("read_csv", "read_parquet", "read_excel"):
            if hasattr(env["pd"], name):
                setattr(env["pd"], name, _block(name))
        env["_path_patched"] = True
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stdout):
            try:
                exec(code, env)
            except Exception:
                traceback.print_exc()
        for num in plt.get_fignums():
            fig = plt.figure(num)
            if out_path:
                path = out_path / f"plot_{num}.png"
            else:
                fd, tmp = tempfile.mkstemp(suffix=".png")
                Path(tmp).unlink()  # remove automatically created empty file
                path = Path(tmp)
            fig.savefig(path)
            plt.close(fig)
            images.append(str(path))
    finally:
        if prev_cwd is not None:
            os.chdir(prev_cwd)
    return {"stdout": stdout.getvalue(), "images": images}
