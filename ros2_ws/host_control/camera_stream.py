import cv2
import threading


class AsynchronousCameraStream:
    def __init__(self, ip_address: str, port: int = 80, path: str = "/stream"):
        self.stream_url = f"http://{ip_address}:{port}{path}"
        self.capture = cv2.VideoCapture(self.stream_url)
        self.grabbed = False
        self.frame = None
        self.active = False
        self.lock = threading.Lock()

        if not self.capture.isOpened():
            raise RuntimeError(
                f"Unable to open camera stream: {self.stream_url}"
            )

        self.active = True
        self.thread = threading.Thread(target=self._update_buffer, daemon=True)
        self.thread.start()

    def _update_buffer(self):
        while self.active:
            grabbed, frame = self.capture.read()
            if grabbed:
                with self.lock:
                    self.grabbed = grabbed
                    self.frame = frame

    def read_latest_frame(self):
        with self.lock:
            return self.grabbed, self.frame

    def stop_stream(self):
        self.active = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.capture.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop_stream()
