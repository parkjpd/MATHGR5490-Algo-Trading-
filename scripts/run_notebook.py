"""Run the notebook with this Python environment and save the finished outputs."""

from pathlib import Path
import json
import sys
import tempfile

import nbformat
from nbclient import NotebookClient
from jupyter_client import KernelManager
from jupyter_client.kernelspec import KernelSpecManager


def main():
    root = Path(__file__).resolve().parents[1]
    path = root / "SPY_Simple_Correlation_Strategy.ipynb"
    notebook = nbformat.read(path, as_version=4)
    nbformat.validate(notebook)
    # Use the Python that launched this script, even if another Jupyter is installed.
    with tempfile.TemporaryDirectory() as directory:
        kernel = Path(directory) / "python3"
        kernel.mkdir()
        (kernel / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "Python 3", "language": "python"}))
        manager = KernelManager(kernel_name="python3",
                                kernel_spec_manager=KernelSpecManager(kernel_dirs=[directory]))
        client = NotebookClient(notebook, km=manager, timeout=120,
                                resources={"metadata": {"path": str(root)}})
        try:
            client.execute()
        finally:
            if manager.has_kernel:
                manager.shutdown_kernel(now=True)
    nbformat.validate(notebook)
    nbformat.write(notebook, path)
    code_cells = sum(cell.cell_type == "code" for cell in notebook.cells)
    print(f"Ran {code_cells} code cells and saved {path.name}")


if __name__ == "__main__":
    main()
