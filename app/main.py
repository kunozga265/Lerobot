"""Entry point for the Robot Maths Tutor (Phase 1: mock robot + mock vision)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from PySide6.QtWidgets import QApplication

from app.gui.main_window import MainWindow

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def main() -> None:
    config = load_config()
    app = QApplication(sys.argv)
    window = MainWindow(config)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
