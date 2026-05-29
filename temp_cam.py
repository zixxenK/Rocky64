import serial
import time
print("OPEN")
with serial.Serial("COM4", 115200, timeout=1) as s:
    s.dtr = False
    time.sleep(0.1)
    s.dtr = True
    time.sleep(2)
    buf = b''
    start = time.time()
    while time.time() - start < 4:
        buf += s.read_all()
    print("RAW:" + buf.decode("ascii", "replace"))
