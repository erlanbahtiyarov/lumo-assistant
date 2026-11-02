# Build on Windows: python -m PyInstaller --noconfirm lumo.spec
from PyInstaller.utils.hooks import collect_all, collect_data_files

binaries, datas, hiddenimports = [], collect_data_files('voice_control_pc'), []
for package in ('faster_whisper', 'ctranslate2', 'tokenizers', 'onnxruntime'):
    extra_data, extra_binary, extra_imports = collect_all(package)
    datas += extra_data
    binaries += extra_binary
    hiddenimports += extra_imports
analysis = Analysis(['scripts/desktop_entry.py'], pathex=['src'], binaries=binaries,
                    datas=datas, hiddenimports=hiddenimports, excludes=['torch', 'torchaudio', 'matplotlib', 'tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'])
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='Lumo',
          debug=False, strip=False, upx=False, console=False, icon='docs/images/lumo-icon.png')
app = COLLECT(exe, analysis.binaries, analysis.datas, name='Lumo', strip=False, upx=False)
