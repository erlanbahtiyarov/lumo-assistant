"""A quiet, warm desktop theme; all components are native Qt widgets."""

STYLE = """
QWidget { font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 13px; color: #263a30; }
QMainWindow, QDialog { background: #f3f3eb; }
QFrame#sidebar { background: #152c23; border-radius: 22px; }
QFrame#sidebar QLabel { color: #ecf0d9; background: transparent; }
QLabel#brand { font-size: 31px; font-weight: 700; letter-spacing: 7px; }
QLabel#eyebrow { font-size: 10px; color: #7d9184; letter-spacing: 2px; }
QLabel#heading { font-size: 32px; font-weight: 600; }
QLabel#subtitle { color: #758076; font-size: 13px; }
QLabel#section { font-size: 17px; font-weight: 600; }
QLabel#dialogTitle { font-size: 23px; font-weight: 600; padding: 12px; }
QLabel#status { background: #e2ebdc; color: #3f654b; border-radius: 13px; padding: 7px 13px; }
QLabel#result { font-size: 19px; font-weight: 500; }
QFrame#card { background: #fffef8; border: 1px solid #e5e7dd; border-radius: 18px; }
QFrame#confirmation { background: #fff2d6; border: 1px solid #dfc68f; border-radius: 12px; }
QLineEdit, QComboBox, QSpinBox { background: #fffef8; border: 1px solid #d7ddcf; border-radius: 9px; padding: 10px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #72947b; }
QPushButton { background: #e9eddf; border: 1px solid #d6dfcd; border-radius: 10px; padding: 11px 16px; font-weight: 500; }
QPushButton:hover { background: #dce5d3; }
QPushButton:pressed { background: #c8d8bd; }
QPushButton:disabled { color: #9da598; background: #eef0e7; border-color: #e1e5d8; }
QPushButton#primary { background: #294e39; color: #f5f6e8; border-color: #294e39; }
QPushButton#primary:hover { background: #386548; }
QPushButton#primary:disabled { background: #a4b39e; border-color: #a4b39e; }
QFrame#sidebar QPushButton { background: #254235; color: #e6e9d4; border-color: #3a5443; }
QFrame#sidebar QPushButton:hover { background: #345440; }
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item { border-bottom: 1px solid #e8eadf; padding: 10px 0; }
QListWidget::item:selected { background: #e9efdf; color: #263a30; border-radius: 6px; }
QTabWidget::pane { border: 1px solid #dce2d3; border-radius: 10px; background: #fafaf3; }
QTabBar::tab { padding: 10px 12px; background: #e5eadb; }
QTabBar::tab:selected { background: #fffef8; }
QCheckBox { spacing: 8px; }
QTableWidget { background: #fffef8; border: 1px solid #dde3d6; gridline-color: #e7eadf; selection-background-color: #dce8d1; }
QHeaderView::section { background: #e8eddf; border: 0; padding: 9px; }
QScrollBar:vertical { background: transparent; width: 8px; }
QScrollBar::handle:vertical { background: #ced8c6; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
