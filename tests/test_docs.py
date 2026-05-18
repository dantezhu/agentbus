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
    assert "nats-server -c /etc/nats-server.conf" in readme
    assert "nats-server -c /etc/nats/agentbus.conf" in readme
    assert "nats --server 'tls://agent-main:agent_main_password@agentbus.example.com:7422' stream ls" in readme


def test_readme_and_example_document_chat_cmd_input_placeholder_and_hermes():
    readme = (ROOT / "README.md").read_text()
    example = (ROOT / "config" / "agentbus.worker.example.toml").read_text()
    skill = (ROOT / "skills" / "agentbus" / "SKILL.md").read_text()

    for text in (readme, example, skill):
        assert "{input}" in text
        assert '["hermes", "chat", "-q", "-Q", "{input}"]' in text


def test_docs_do_not_recommend_environment_variable_configuration():
    readme = (ROOT / "README.md").read_text()
    example = (ROOT / "config" / "agentbus.worker.example.toml").read_text()
    skill = (ROOT / "skills" / "agentbus" / "SKILL.md").read_text()

    for text in (readme, example, skill):
        assert "export NATS_URL" not in text
        assert "AGENT_CHAT_CMD" not in text
        assert "AGENTBUS_LOG_DIR" not in text


def test_docs_use_direct_cli_args_for_publish_not_config_files():
    readme = (ROOT / "README.md").read_text()
    skill = (ROOT / "skills" / "agentbus" / "SKILL.md").read_text()

    for text in (readme, skill):
        assert "agentbus task publish --config" not in text
        assert "--nats-url" in text
        assert "--to" in text
        assert "--task-type" in text
        assert "--task " not in text
        assert "--reply-to-agent" not in text
        assert "--subject" not in text
        assert "--task-id" not in text
        assert "--risk-level" not in text
        assert "--max-hops" not in text
        assert "code ping" not in text


def test_deploy_templates_use_env_virtualenv_path():
    systemd = (ROOT / "deploy" / "systemd" / "agentbus-worker.service").read_text()
    launchd = (ROOT / "deploy" / "launchd" / "com.agentbus.worker.plist").read_text()
    supervisor = (ROOT / "deploy" / "supervisor" / "agentbus-worker.conf").read_text()

    for text in (systemd, launchd, supervisor):
        assert "/path/to/agentbus/env/bin/agentbus" in text
        assert ".venv" not in text

    assert "command=/path/to/agentbus/env/bin/agentbus worker run --config" in supervisor
    assert "autorestart=true" in supervisor
