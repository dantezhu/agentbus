import logging
from logging.handlers import RotatingFileHandler

from agentbus.cli import configure_logging


def test_configure_logging_creates_default_log_file_in_log_dir(tmp_path):
    log_dir = tmp_path / ".agentbus" / "logs"
    worker_log_file = log_dir / "agentbus-worker.log"

    configure_logging("INFO", log_dir=str(log_dir), log_max_bytes=100, log_backup_count=2, force=True)
    logging.getLogger("agentbus.test").info("hello agentbus log")

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert worker_log_file.exists()
    assert "hello agentbus log" in worker_log_file.read_text()
    file_handlers = [handler for handler in logging.getLogger().handlers if isinstance(handler, RotatingFileHandler)]
    assert file_handlers[0].maxBytes == 100
    assert file_handlers[0].backupCount == 2
