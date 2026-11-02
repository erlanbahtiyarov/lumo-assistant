from voice_control_pc.config import load_config_bundle
from voice_control_pc.models import AppEntry
from voice_control_pc.nlu import RuleBasedNLU


def test_catalog_system_targets_work_with_opening_verbs(tmp_path):
    c = load_config_bundle(tmp_path)
    nlu = RuleBasedNLU(c.commands, c.apps)
    assert nlu.match("запусти терминал").intent == "open_terminal"
    assert nlu.match("покажи диспетчер задач").intent == "open_task_manager"


def test_alias_collision_does_not_choose_an_arbitrary_object(tmp_path):
    c = load_config_bundle(tmp_path)
    c.apps.applications["редактор"] = AppEntry(aliases=["блокнот"], launch=["editor.exe"])
    nlu = RuleBasedNLU(c.commands, c.apps)
    assert nlu.match("открой блокнот").intent is None


def test_explicit_folder_does_not_open_application_with_same_alias(tmp_path):
    c = load_config_bundle(tmp_path)
    c.apps.applications["документы"] = AppEntry(aliases=["документы"], launch=["editor.exe"])
    nlu = RuleBasedNLU(c.commands, c.apps)
    assert nlu.match("открой документы").intent is None
    match = nlu.match("открой папку документы")
    assert match.intent == "open_folder"
    assert match.slots == {"folder_name": "документы"}
