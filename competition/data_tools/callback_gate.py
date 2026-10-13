"""Drain all callbacks admitted before the explicit intake cutoff; ROS-independent."""
import threading


class CallbackGate:
    def __init__(self):
        self.condition = threading.Condition()
        self.accepting = True
        self.active = 0
        self.admitted = 0

    def run(self, callback, *args):
        with self.condition:
            if not self.accepting:
                return False  # Before taking receipt timestamps: outside capture boundary.
            self.active += 1
            self.admitted += 1
        try:
            callback(*args)
        finally:
            with self.condition:
                self.active -= 1
                self.condition.notify_all()
        return True

    def close_intake(self):
        with self.condition:
            self.accepting = False

    def drain(self):
        with self.condition:
            while self.active:
                self.condition.wait()
