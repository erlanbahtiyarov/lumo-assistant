"""Render the actual native widgets for visual review without microphone access."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QTabWidget

from voice_control_pc.config import load_config_bundle
from voice_control_pc.gui import LumoWindow
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
        from importlib.resources import files

        icon = QIcon(str(files("voice_control_pc.resources").joinpath("lumo.svg")))
        icon.pixmap(256, 256).save(str(output / "lumo-icon.png"))
        dialog.close()
        window.close()
    print(f"Native widget previews saved to {output}")


if __name__ == "__main__":
    main()
