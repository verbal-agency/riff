import json

from riff.config import Settings
from riff.worker import run_worker


def test_worker_emits_structured_completion_event(capsys):
    settings = Settings("postgresql://user:password@localhost:5432/riff", environment="test")
    run_id = run_worker(settings)
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record["message"] == "worker.completed"
    assert record["fields"]["run_id"] == run_id
    assert record["fields"]["status"] == "success"
    assert record["fields"]["stages"] == []
    assert "password" not in captured.out
    assert "password" not in captured.err
