from pathlib import Path

from voice_control_pc import cli
from voice_control_pc.config import load_config_bundle


def test_listen_creates_artifacts_on_first_run(tmp_path, monkeypatch, capsys):
    config = load_config_bundle(Path(__file__).resolve().parents[1])
    config.project_root = tmp_path
    monkeypatch.setattr(cli, "load_config_bundle", lambda root: config)
    monkeypatch.setattr("sys.argv", ["lumo", "listen", "--dry-run"])

    class Transcriber:
        def __init__(self, settings):
            pass

        def transcribe_file(self, path):
            assert path.is_file()
            return "открой браузер"

    def record(output_path, **kwargs):
        assert output_path.parent.is_dir()
        output_path.write_bytes(b"test")

    monkeypatch.setattr(cli, "FasterWhisperTranscriber", Transcriber)
    monkeypatch.setattr(cli, "record_microphone_to_wav", record)
    assert cli.main() == 0
    assert '"dry_run"' in capsys.readouterr().out
