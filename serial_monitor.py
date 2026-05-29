import os
import serial
import sys
import time

PORT = os.environ.get("SERIAL_PORT", "AUTO")
BAUD = 115200
MAX_RETRIES = 3
RETRY_DELAY = 1.0

try:
    from serial.tools import list_ports
    ports = list_ports.comports()
    if not ports:
        raise serial.SerialException("No serial ports found")

    print("Detected serial ports:")
    for p in ports:
        print(f"  {p.device} - {p.description} - {p.hwid}")

    if PORT == "AUTO":
        candidate_ports = [p.device for p in ports if p.device not in ('COM1', 'COM2')]
        if 'COM4' in [p.device for p in ports]:
            candidate_ports = ['COM4'] + [p for p in candidate_ports if p != 'COM4']
    else:
        candidate_ports = [PORT]

    if not candidate_ports:
        raise serial.SerialException("No candidate ports found")

    ser = None
    for candidate in candidate_ports:
        try:
            print(f"Trying {candidate}...")
            ser = serial.Serial(candidate, BAUD, timeout=0.5, dsrdtr=False, rtscts=False, xonxoff=False)
            PORT = candidate
            break
        except Exception as exc:
            print(f"Could not open {candidate}: {type(exc).__name__}: {exc}")
            ser = None

    if ser is None:
        raise serial.SerialException("No serial ports could be opened")

    with ser:
        print(f"Opened {PORT} at {BAUD}")
        print("Port settings:")
        try:
            settings = ser.get_settings()
            for k, v in settings.items():
                print(f"  {k}: {v}")
        except Exception as exc:
            print(f"  Could not read settings: {type(exc).__name__}: {exc}")

        try:
            ser.setDTR(False)
            ser.setRTS(False)
            time.sleep(0.1)
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception as exc:
            print(f"Warning: could not reset control lines/buffers: {type(exc).__name__}: {exc}")

        print("Press Ctrl+C to exit.")
        print("Press RESET on the ESP32 once after the monitor starts.")
        retry_count = 0
        while True:
            try:
                data = ser.read(1)
                if data:
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()
                else:
                    time.sleep(0.05)
            except serial.SerialException as exc:
                text = str(exc)
                if "ClearCommError failed" in text and retry_count < MAX_RETRIES:
                    retry_count += 1
                    print(f"Serial read failed on attempt {retry_count}/{MAX_RETRIES}: {text}")
                    print("Attempting to reopen the port after delay...")
                    try:
                        ser.close()
                    except Exception:
                        pass
                    time.sleep(RETRY_DELAY)
                    try:
                        ser = serial.Serial(PORT, BAUD, timeout=0.5, dsrdtr=False, rtscts=False, xonxoff=False)
                        ser.setDTR(False)
                        ser.setRTS(False)
                        time.sleep(0.1)
                        ser.reset_input_buffer()
                        ser.reset_output_buffer()
                        print("Reopened port successfully.")
                        continue
                    except Exception as reopen_exc:
                        print(f"Reopen failed: {type(reopen_exc).__name__}: {reopen_exc}")
                        break
                if "ClearCommError failed" in text:
                    print("Serial read failed: ClearCommError failed. This often means the USB-serial driver or device is not ready.")
                    print("Try unplugging/re-plugging the board, closing any other serial monitor, or using a different USB cable.")
                else:
                    print(f"Serial read failed: {type(exc).__name__}: {exc}")
                break
            except Exception as exc:
                print(f"Serial read failed: {type(exc).__name__}: {exc}")
                break
except Exception as exc:
    print(f"Serial error: {type(exc).__name__}: {exc}")
except KeyboardInterrupt:
    print("\nExited monitor.")
