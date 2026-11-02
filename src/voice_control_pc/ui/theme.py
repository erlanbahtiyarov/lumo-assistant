"""Charcoal and ivory native widgets, shared by the app and its companion."""

from importlib.resources import files

STYLE = """
QWidget { font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; color: #eeeae1; }
QMainWindow, QDialog { background: #111214; }
QFrame#sidebar { background: #191a1d; border: 1px solid #292b30; border-radius: 16px; }
QFrame#sidebar QLabel { background: transparent; }
QLabel#brand { font-size: 29px; font-weight: 700; letter-spacing: 5px; }
QLabel#eyebrow { font-size: 10px; color: #92949c; letter-spacing: 1px; }
QLabel#heading { font-size: 30px; font-weight: 600; }
QLabel#subtitle { color: #a4a5ad; font-size: 12px; }
QLabel#section { font-size: 16px; font-weight: 600; }
QLabel#dialogTitle { font-size: 22px; font-weight: 600; padding: 12px; }
QLabel#status { background: #252629; color: #ded9ca; border: 1px solid #38393d; border-radius: 8px; padding: 6px 11px; font-size: 11px; }
QLabel#result { font-size: 19px; font-weight: 500; }
QFrame#card { background: #1a1b1e; border: 1px solid #2d2e33; border-radius: 14px; }
QFrame#confirmation { background: #302b20; border: 1px solid #766343; border-radius: 8px; }
QLineEdit, QComboBox, QSpinBox { background: #121315; border: 1px solid #3a3b41; border-radius: 8px; padding: 10px; selection-background-color: #615d51; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #c8c1ad; }
QSpinBox { padding: 10px 30px 10px 12px; }
QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 26px; background: #303136; border-top-right-radius: 7px; }
QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 26px; background: #303136; border-bottom-right-radius: 7px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #494a52; }
QSpinBox::up-arrow { image: url('@CHEVRON_UP@'); width: 10px; height: 6px; }
QSpinBox::down-arrow, QComboBox::down-arrow { image: url('@CHEVRON_DOWN@'); width: 10px; height: 6px; }
QComboBox::drop-down { width: 28px; border: 0; background: #303136; border-top-right-radius: 7px; border-bottom-right-radius: 7px; }
QComboBox QAbstractItemView { background: #222327; color: #eeeae1; selection-background-color: #45433c; }
QPushButton { background: #292a2e; border: 1px solid #3b3c42; border-radius: 8px; padding: 11px 16px; font-weight: 500; }
QPushButton:hover { background: #37383e; border-color: #65666e; }
QPushButton:pressed { background: #414249; }
QPushButton:disabled { color: #686971; background: #202125; border-color: #2b2c31; }
QPushButton#primary { background: #e9e3d3; color: #18191b; border-color: #e9e3d3; }
QPushButton#primary:hover { background: #fff8e6; border-color: #fff8e6; }
QPushButton#primary:disabled { background: #55534d; color: #a8a59b; border-color: #55534d; }
QFrame#sidebar QPushButton { text-align: left; background: #232428; border-color: #34353b; }
QFrame#sidebar QPushButton:hover { background: #34353b; }
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item { border-bottom: 1px solid #303137; padding: 10px 0; }
QListWidget::item:selected { background: #323238; color: #f1e9d5; border-radius: 6px; }
QTabWidget::pane { border: 1px solid #36373e; border-radius: 8px; background: #191a1e; }
QTabBar::tab { padding: 10px 12px; background: #202125; color: #a9aab0; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { background: #2b2c31; color: #f1e9d5; border-bottom-color: #e4dcc6; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; background: #161719; border: 1px solid #72737b; border-radius: 4px; }
QCheckBox::indicator:checked { background: #e5decb; border: 4px solid #686457; }
QTableWidget { background: #191a1e; border: 1px solid #383940; gridline-color: #34353c; selection-background-color: #444239; }
QHeaderView::section { background: #292a30; border: 0; padding: 9px; }
QMenu { background: #1a1b1f; border: 1px solid #44454b; padding: 5px; }
QMenu::item { padding: 8px 24px; border-radius: 4px; }
QMenu::item:selected { background: #3a3934; }
QToolTip { background: #292a2e; color: #eeeae1; border: 1px solid #55565e; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #494a52; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""

for direction in ("up", "down"):
    asset = str(files("voice_control_pc.resources").joinpath(f"chevron-{direction}.svg"))
    STYLE = STYLE.replace(f"@CHEVRON_{direction.upper()}@", asset.replace("\\", "/"))


def apply_theme(app):
    """Give platform controls and dialogs the same readable dark palette."""
    from PySide6.QtGui import QColor, QPalette

    if app.property("lumo_theme_applied"):
        return
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: "#111214",
        QPalette.ColorRole.WindowText: "#eeeae1",
        QPalette.ColorRole.Base: "#191a1e",
        QPalette.ColorRole.AlternateBase: "#24252a",
        QPalette.ColorRole.Text: "#eeeae1",
        QPalette.ColorRole.Button: "#292a2e",
        QPalette.ColorRole.ButtonText: "#eeeae1",
        QPalette.ColorRole.Highlight: "#615d51",
        QPalette.ColorRole.HighlightedText: "#fff8e6",
        QPalette.ColorRole.PlaceholderText: "#93949c",
        QPalette.ColorRole.ToolTipBase: "#292a2e",
        QPalette.ColorRole.ToolTipText: "#eeeae1",
    }.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#686971"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#686971"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    app.setProperty("lumo_theme_applied", True)
