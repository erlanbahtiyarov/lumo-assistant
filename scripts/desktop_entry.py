"""PyInstaller entry point; invokes the same native app as lumo-desktop."""

from voice_control_pc.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
