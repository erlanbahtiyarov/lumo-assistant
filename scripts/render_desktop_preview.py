"""Render the actual native widgets for visual review without microphone access."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QIcon, QImage, QPainter
from PySide6.QtWidgets import QApplication, QTabWidget

from voice_control_pc.config import load_config_bundle
from voice_control_pc.diagnostics import check_readiness
from voice_control_pc.gui import LumoWindow
from voice_control_pc.ui.diagnostics import ReadinessDialog
from voice_control_pc.ui.settings import SettingsDialog


def main():
    output = Path(__file__).resolve().parents[1] / "docs" / "images"
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    with tempfile.TemporaryDirectory(prefix="lumo-preview-") as directory:
        window = LumoWindow(load_config_bundle(Path(directory)))
        window.show()
        app.processEvents()
        window.grab().save(str(output / "lumo-desktop.png"))
        window.pet.set_state("idle")
        window.pet.grab().save(str(output / "lumo-pet.png"))
        window.pet.set_state("listening")
        app.processEvents()
        window.pet.panel.grab().save(str(output / "lumo-pet-listening.png"))
        dialog = SettingsDialog(window.config, [], window)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output / "lumo-settings.png"))
        dialog.findChild(QTabWidget).setCurrentIndex(1)
        app.processEvents()
        dialog.grab().save(str(output / "lumo-pet-settings.png"))
        dialog.findChild(QTabWidget).setCurrentIndex(3)
        app.processEvents()
        dialog.grab().save(str(output / "lumo-app-settings.png"))
        dialog.close()
        report = ReadinessDialog(check_readiness(window.config), window)
        report.show()
        app.processEvents()
        report.grab().save(str(output / "lumo-readiness.png"))
        report.close()
        from importlib.resources import files

        icon = QIcon(str(files("voice_control_pc.resources").joinpath("lumo.svg")))
        canvas = QImage(256, 256, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        icon.paint(painter, QRect(0, 0, 256, 256))
        painter.end()
        canvas.save(str(output / "lumo-icon.png"))
        dialog.close()
        window.close()
    print(f"Native widget previews saved to {output}")


if __name__ == "__main__":
    main()
