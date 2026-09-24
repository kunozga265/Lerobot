"""Entry point for Arithma. `robot.mode` / `vision.mode` in config.yaml
choose mock or real parts (see app/hardware.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from PySide6.QtWidgets import QApplication, QMessageBox

from app.gui.main_window import MainWindow
from app.hardware import HardwareError, build_hardware

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def main() -> None:
    config = load_config()
    app = QApplication(sys.argv)
    try:
        hardware = build_hardware(config)
    except HardwareError as e:
        QMessageBox.critical(None, "Arithma: hardware problem", str(e))
        sys.exit(1)
    window = MainWindow(config, hardware)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
