import signal
import threading

from app.bootstrap.backup_scheduler import BackupScheduler


if __name__ == "__main__":
    stop_event = threading.Event()

    def handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    BackupScheduler(
        sleep_fn=stop_event.wait,
        stop_requested=stop_event.is_set,
    ).run()
