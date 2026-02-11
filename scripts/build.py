"""PyInstaller 빌드 스크립트."""

import subprocess
import sys


def main() -> None:
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "aion2meter",
        "--hidden-import", "winocr",
        "--hidden-import", "pytesseract",
        "--hidden-import", "matplotlib.backends.backend_qtagg",
        "src/aion2meter/__main__.py",
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
