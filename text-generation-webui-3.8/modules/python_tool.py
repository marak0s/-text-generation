import io
import contextlib
import tempfile
from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd

from modules import dataset_tool


def execute_python(code: str):
    """Execute arbitrary Python code and capture stdout and generated images.

    Returns a dict with 'stdout' and 'images' keys. Images are file paths to
    any matplotlib figures created by the code.
    """
    local_vars = {}
    stdout = io.StringIO()
    images: list[str] = []
    with contextlib.redirect_stdout(stdout):
        exec(code, {"plt": plt, "pd": pd, "get_table_path": dataset_tool.get_table_path}, local_vars)
        for num in plt.get_fignums():
            fig = plt.figure(num)
            fd, path = tempfile.mkstemp(suffix=".png")
            Path(path).unlink()  # remove automatically created empty file
            fig.savefig(path)
            plt.close(fig)
            images.append(path)
    return {"stdout": stdout.getvalue(), "images": images}
