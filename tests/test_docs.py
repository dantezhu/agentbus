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
    assert "https://github.com/nats-io/natscli" in readme
    assert "https://docs.nats.io/running-a-nats-service/introduction/installation" in readme
    assert "nats-server -c /etc/nats-server.conf" in readme
    assert "nats-server -c /etc/nats/agentbus.conf" in readme
    assert "store_dir: \"/data/nats\"" in readme
    assert "jetstream: enabled" in readme
    assert "JetStream not enabled for account (10039)" in readme
    assert "/data/jetstream" not in readme
    assert "sudo chmod 600 /etc/nats-server.conf" not in readme
    assert "sudo chown -R nats:nats /data" not in readme
    assert "nats --server 'nats://main:main_password@agentbus.example.com:7422' stream ls" in readme


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


def test_docs_do_not_expose_derived_worker_routing_fields():
    readme = (ROOT / "README.md").read_text()
    example = (ROOT / "config" / "agentbus.worker.example.toml").read_text()
    skill = (ROOT / "skills" / "agentbus" / "SKILL.md").read_text()

    for text in (readme, example, skill):
        assert "task_subject =" not in text
        assert "default_result_subject =" not in text
        assert "durable =" not in text

    assert "task subject" in readme
    assert "result subject" in readme
    assert "durable" in readme


def test_docs_use_direct_cli_args_for_publish_not_config_files():
    readme = (ROOT / "README.md").read_text()
    skill = (ROOT / "skills" / "agentbus" / "SKILL.md").read_text()

    for text in (readme, skill):
        assert "agentbus task publish --config" not in text
        assert "--server-url" in text
        assert "--to" in text
        assert "--task-type" in text
        assert "--task " not in text
        assert "--reply-to-agent" not in text
        assert "--subject" not in text
        assert "--task-id" not in text
        assert "--risk-level" not in text
        assert "--max-hops" not in text
        assert "--payload-fmt" not in text
        assert "payload.fmt" not in text
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


def test_readme_layout_lists_primary_project_files_as_tree():
    readme = (ROOT / "README.md").read_text()

    assert "├── agentbus/" in readme
    assert "│   ├── __init__.py" in readme
    assert "│   ├── cli.py" in readme
    assert "│   ├── config.py" in readme
    assert "│   ├── messages.py" in readme
    assert "│   ├── publish.py" in readme
    assert "│   ├── result.py" in readme
    assert "│   └── worker.py" in readme
    assert "├── config/" in readme
    assert "│   ├── agentbus.worker.example.toml" in readme
    assert "│   └── nats-server.conf" in readme
    assert "├── deploy/" in readme
    assert "│   ├── launchd/com.agentbus.worker.plist" in readme
    assert "│   ├── supervisor/agentbus-worker.conf" in readme
    assert "│   └── systemd/agentbus-worker.service" in readme
    assert "├── scripts/" in readme
    assert "│   └── stream-setup.sh" in readme
    assert "├── skills/" in readme
    assert "│   └── agentbus/SKILL.md" in readme
    assert "├── tests/" in readme
    assert "│   └── test_*.py" in readme
    assert "├── LICENSE" in readme
    assert "├── README.md" in readme
    assert "├── pyproject.toml" in readme
    assert "├── requirements-dev.txt" in readme
    assert "└── requirements.txt" in readme
