import io
import contextlib
import tempfile
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from modules import dataset_tool


def execute_python(code: str, out_dir: str | Path | None = None):
    """Execute arbitrary Python code and capture stdout and generated images.

    Returns a dict with 'stdout' and 'images' keys. Images are file paths to
    any matplotlib figures created by the code. If ``out_dir`` is provided,
    images are saved under that directory.
    """
    local_vars = {}
    stdout = io.StringIO()
    images: list[str] = []
    out_path = Path(out_dir) if out_dir else None
    if out_path:
        out_path.mkdir(parents=True, exist_ok=True)
    with contextlib.redirect_stdout(stdout):
        exec(code, {"plt": plt, "pd": pd, "get_table_path": dataset_tool.get_table_path}, local_vars)
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
    return {"stdout": stdout.getvalue(), "images": images}
