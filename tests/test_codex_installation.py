import pytest

from paperrule.integrations.codex.install import INSTRUCTION, MARKER, SKILL, install, uninstall


@pytest.fixture
def paper(tmp_path):
    root = tmp_path / "synthetic-paper"
    root.mkdir()
    return root


@pytest.mark.parametrize(
    "original",
    [
        b"Keep these original instructions",
        b"Keep these original instructions\n\n",
        b"\xef\xbb\xbfKeep original UTF-8 BOM and Windows newlines\r\n\r\n",
        b"",
    ],
)
def test_install_uninstall_preserves_original_instruction_bytes(paper, original):
    agents = paper / "AGENTS.md"
    agents.write_bytes(original)
    result = install(paper)
    assert result["skill_created"] is True
    installed = agents.read_bytes()
    assert installed.startswith(original)
    assert install(paper) == {"skill_created": False, "instructions_added": False}
    assert agents.read_bytes() == installed
    assert uninstall(paper) == {"skill_removed": True, "instructions_removed": True}
    assert agents.read_bytes() == original
    assert uninstall(paper) == {"skill_removed": False, "instructions_removed": False}
    assert agents.read_bytes() == original


def test_uninstall_preserves_instructions_added_after_installation(paper):
    agents = paper / "AGENTS.md"
    original = b"Keep original project instructions"
    following = b"\nKeep instructions added later.\n"
    agents.write_bytes(original)
    install(paper)
    agents.write_bytes(agents.read_bytes() + following)
    uninstall(paper)
    assert agents.read_bytes() == original + following


def test_uninstall_of_legacy_block_does_not_truncate_following_user_content(paper):
    agents = paper / "AGENTS.md"
    prefix = b"Existing user instructions.\n"
    suffix = b"Instructions added after the old PaperRule installer.\n"
    legacy = (MARKER + "\n" + INSTRUCTION + "\n").encode("utf-8")
    agents.write_bytes(prefix + legacy + suffix)
    uninstall(paper)
    assert agents.read_bytes() == prefix + suffix


def test_existing_custom_skill_is_not_overwritten_or_referenced_by_a_new_block(paper):
    skill = paper / ".agents" / "skills" / "paperrule" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    custom = b"Synthetic user-managed skill, preserve exactly."
    skill.write_bytes(custom)
    agents = paper / "AGENTS.md"
    agents.write_bytes(b"Synthetic project instructions.")
    with pytest.raises(ValueError, match="user-managed"):
        install(paper)
    assert skill.read_bytes() == custom
    assert agents.read_bytes() == b"Synthetic project instructions."


def test_edited_managed_block_is_preserved_for_review(paper):
    install(paper)
    agents = paper / "AGENTS.md"
    edited = agents.read_bytes().replace(INSTRUCTION.encode(), b"Synthetic user edit.")
    agents.write_bytes(edited)
    with pytest.raises(ValueError, match="edited"):
        uninstall(paper)
    assert agents.read_bytes() == edited
    assert (paper / ".agents" / "skills" / "paperrule" / "SKILL.md").read_bytes() == SKILL.encode()


def test_user_edits_to_installed_skill_are_preserved(paper):
    agents = paper / "AGENTS.md"
    agents.write_bytes(b"Original project instructions.")
    install(paper)
    skill = paper / ".agents" / "skills" / "paperrule" / "SKILL.md"
    edited = skill.read_bytes() + b"\nSynthetic user-added guidance.\n"
    skill.write_bytes(edited)
    result = uninstall(paper)
    assert result["skill_removed"] is False
    assert skill.read_bytes() == edited
    assert agents.read_bytes() == b"Original project instructions."


def test_user_scope_uses_injected_home_and_preserves_existing_files(paper, tmp_path):
    home = tmp_path / "synthetic-home"
    home.mkdir()
    home_agents = home / "AGENTS.md"
    home_agents.write_bytes(b"Keep synthetic home instructions.")
    project_agents = paper / "AGENTS.md"
    original = b"Keep synthetic paper instructions."
    project_agents.write_bytes(original)
    result = install(paper, "user", user_home=home)
    assert result == {"skill_created": True, "instructions_added": True}
    skill = home / ".agents" / "skills" / "paperrule" / "SKILL.md"
    assert skill.read_bytes() == SKILL.encode()
    assert not (paper / ".agents").exists()
    assert install(paper, "user", user_home=home) == {
        "skill_created": False, "instructions_added": False,
    }
    assert uninstall(paper, "user", user_home=home) == {
        "skill_removed": True, "instructions_removed": True,
    }
    assert project_agents.read_bytes() == original
    assert home_agents.read_bytes() == b"Keep synthetic home instructions."
    assert not skill.exists()


def test_user_scope_refuses_to_overwrite_existing_shared_skill(paper, tmp_path):
    home = tmp_path / "synthetic-home"
    skill = home / ".agents" / "skills" / "paperrule" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(b"Keep synthetic custom shared skill.")
    with pytest.raises(ValueError, match="user-managed"):
        install(paper, "user", user_home=home)
    assert skill.read_bytes() == b"Keep synthetic custom shared skill."
    assert not (paper / "AGENTS.md").exists()


def test_unknown_scope_does_not_modify_project(paper):
    with pytest.raises(ValueError, match="Scope must be"):
        install(paper, "invalid")
    assert list(paper.iterdir()) == []


def test_symlink_cannot_redirect_integration_outside_selected_project(paper, tmp_path):
    outside = tmp_path / "synthetic-outside"
    outside.mkdir()
    try:
        (paper / ".agents").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks is unavailable in this environment")
    with pytest.raises(ValueError, match="inside"):
        install(paper)
    assert list(outside.iterdir()) == []
