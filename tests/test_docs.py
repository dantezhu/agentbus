from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_uses_env_virtualenv_and_plain_pip_commands():
    readme = (ROOT / "README.md").read_text()

    assert "python3 -m venv env" in readme
    assert "source env/bin/activate" in readme
    assert "pip install --upgrade pip" in readme
    assert "pip install agentbus" in readme
    assert "python3 -m venv .venv" not in readme
    assert "source .venv/bin/activate" not in readme
    assert "python -m pip" not in readme


def test_readme_documents_nats_server_source_and_install_steps():
    readme = (ROOT / "README.md").read_text()

    assert "https://github.com/nats-io/nats-server" in readme
    assert "https://docs.nats.io/running-a-nats-service/introduction/installation" in readme
    assert "nats-server -c /etc/nats/agentbus.conf" in readme
    assert "nats --server \"$NATS_URL\" stream ls" in readme


def test_readme_and_example_document_chat_cmd_input_placeholder_and_hermes():
    readme = (ROOT / "README.md").read_text()
    example = (ROOT / "config" / "agentbus.worker.example.toml").read_text()
    skill = (ROOT / "skills" / "agentbus" / "SKILL.md").read_text()

    for text in (readme, example, skill):
        assert "{input}" in text
        assert "hermes chat -q -Q {input}" in text


def test_deploy_templates_use_env_virtualenv_path():
    systemd = (ROOT / "deploy" / "systemd" / "agentbus-worker.service").read_text()
    launchd = (ROOT / "deploy" / "launchd" / "com.agentbus.worker.plist").read_text()

    assert "/path/to/agentbus/env/bin/agentbus" in systemd
    assert "/path/to/agentbus/env/bin/agentbus" in launchd
    assert ".venv" not in systemd
    assert ".venv" not in launchd
