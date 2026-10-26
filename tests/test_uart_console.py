"""Exercise the actual POSIX serial implementation through a pseudo-terminal."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import pty
import select
import tempfile
import termios
import threading
import time
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "uart_console.py"
spec = importlib.util.spec_from_file_location("uart_console", SOURCE)
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class Device:
    def __init__(self, *, corrupt_ping=False, silent=False, frozen_blink=False):
        self.master, self.slave = pty.openpty()
        self.path = os.ttyname(self.slave)
        self.original = termios.tcgetattr(self.slave)
        self.stop = threading.Event()
        self.corrupt_ping = corrupt_ping
        self.silent = silent
        self.commands = []
        self.led = "off"
        self.motor = "off"
        self.speed = 25
        self.edges = 0
        self.started = time.monotonic()
        self.last_edge = self.started
        self.frozen_blink = frozen_blink
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def period(self):
        return 2000 - 18 * self.speed if self.motor == "on" and self.speed else 0

    def update_blink(self):
        period = self.period()
        if period and not self.frozen_blink:
            half_seconds = period / 2000
            count = int((time.monotonic() - self.last_edge) / half_seconds)
            self.edges += count
            self.last_edge += count * half_seconds
            if count % 2:
                self.led = "off" if self.led == "on" else "on"

    def run(self):
        buf = bytearray()
        while not self.stop.is_set():
            if not select.select([self.master], [], [], 0.02)[0]:
                continue
            try:
                buf.extend(os.read(self.master, 4096))
            except OSError:
                break
            while b"\n" in buf:
                raw, _, rest = buf.partition(b"\n")
                buf[:] = rest
                command = raw.decode().strip("\r")
                self.commands.append(command)
                self.update_blink()
                if self.silent:
                    continue
                if not command:
                    reply = ""
                elif command == "info":
                    reply = "board=NUCLEO-G474RE mcu=STM32G474RE uart=LPUART1 baud=115200"
                elif command.startswith("ping "):
                    reply = "PONG wrong" if self.corrupt_ping else "PONG " + command[5:]
                elif command in ("motor on", "motor off"):
                    self.motor = command[6:]
                    self.led = "on" if self.period() else "off"
                    self.last_edge = time.monotonic()
                    reply = f"OK motor={self.motor} mode=led_simulation"
                elif command.startswith("speed "):
                    value = command[6:]
                    if value == "up":
                        requested = min(100, self.speed + 10)
                    elif value == "down":
                        requested = max(0, self.speed - 10)
                    elif value.isascii() and value.isdigit() and int(value) <= 100:
                        requested = int(value)
                    else:
                        requested = None
                    if requested is None:
                        reply = "ERR speed must be 0..100, up, or down"
                    else:
                        self.speed = requested
                        self.last_edge = time.monotonic()
                        self.led = "on" if self.period() else "off"
                        reply = f"OK speed_pct={self.speed}"
                elif command in ("led on", "led off"):
                    if self.motor == "on":
                        reply = "ERR motor simulation active"
                    else:
                        self.led = command[4:]
                        reply = "OK led=" + self.led
                elif command == "status":
                    uptime = int((time.monotonic() - self.started) * 1000)
                    reply = (f"uptime_ms={uptime} led={self.led} rx_errors=0 mode=led_simulation "
                             f"motor={self.motor} speed_pct={self.speed} "
                             f"blink_period_ms={self.period()} blink_edges={self.edges}")
                elif command.startswith("echo "):
                    reply = "ECHO " + command[5:]
                elif len(command) > 127:
                    reply = "ERR line too long (max 127)"
                else:
                    reply = "ERR unknown command"
                # Deliberately fragment the prompt across writes.
                os.write(self.master, (reply + "\r\nmot").encode())
                time.sleep(0.001)
                os.write(self.master, b"or> ")

    def close(self):
        self.stop.set()
        self.worker.join(timeout=1)
        os.close(self.slave)
        os.close(self.master)


class ConsoleTests(unittest.TestCase):
    def assert_restored(self, device):
        actual = termios.tcgetattr(device.slave)
        expected = list(device.original)
        # macOS sets PENDIN when returning to canonical input. This is queued
        # input status maintained by the kernel, not a configuration mismatch.
        actual[3] &= ~getattr(termios, "PENDIN", 0)
        expected[3] &= ~getattr(termios, "PENDIN", 0)
        self.assertEqual(actual, expected)

    def call(self, device, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = console.main(["--port", device.path, "--timeout", "0.5", *args])
        return code, output.getvalue()

    def test_full_demo_and_timestamped_transcript(self):
        device = Device()
        try:
            with tempfile.TemporaryDirectory() as directory:
                log = Path(directory) / "nested" / "logs" / "session.log"
                code, output = self.call(device, "--demo", "--log", str(log))
                self.assertEqual(code, 0, output)
                self.assertIn("100/100 distinct ping roundtrips", output)
                transcript = log.read_text()
                self.assertRegex(transcript, r"\d{4}-\d\d-\d\dT.*\+00:00 TX ping")
                self.assertIn("RESULT PASS:", transcript)
                self.assertIn("MEASURE motor=on speed_pct=25", transcript)
                self.assertIn("MEASURE motor=on speed_pct=100", transcript)
                self.assertIn("PASS: LED motor simulation", output)
                pings = [s for s in device.commands if s.startswith("ping ")]
                self.assertEqual(len(pings), 102)
                self.assertEqual(len(set(pings)), 102)
                self.assertIn("x" * 512, device.commands)
                self.assertEqual(device.led, "off")
                self.assertEqual((device.motor, device.speed), ("off", 25))
                self.assert_restored(device)
        finally:
            device.close()

    def test_command_and_error_exit_code(self):
        device = Device()
        try:
            code, output = self.call(device, "--command", "ping hello")
            self.assertEqual((code, output.strip()), (0, "PONG hello"))
            code, output = self.call(device, "--command", "invalid")
            self.assertEqual(code, 1)
            self.assertIn("ERR unknown command", output)
        finally:
            device.close()

    def test_demo_rejects_incorrect_ping(self):
        device = Device(corrupt_ping=True)
        try:
            code, output = self.call(device, "--demo")
            self.assertEqual(code, 1)
            self.assertIn("initial ping mismatch", output)
            self.assert_restored(device)
        finally:
            device.close()

    def test_echo_prompt_text_does_not_terminate_reply(self):
        device = Device()
        try:
            code, output = self.call(device, "--command", "echo motor> foo")
            self.assertEqual((code, output.strip()), (0, "ECHO motor> foo"))
        finally:
            device.close()

    def test_demo_rejects_nonblinking_simulation(self):
        device = Device(frozen_blink=True)
        try:
            code, output = self.call(device, "--demo")
            self.assertEqual(code, 1)
            self.assertIn("25% speed blink rate incorrect", output)
        finally:
            device.close()

    def test_timeout_and_restoration(self):
        device = Device(silent=True)
        try:
            code, output = self.call(device, "--command", "ping")
            self.assertEqual(code, 1)
            self.assertIn("Timed out", output)
            self.assert_restored(device)
        finally:
            device.close()

    def test_ambiguous_port_requires_selection(self):
        with mock.patch.object(console, "ports", return_value=["/dev/a", "/dev/b"]):
            with self.assertRaisesRegex(console.ConsoleError, "Multiple UART ports"):
                console.choose_port(None)
            self.assertEqual(console.choose_port("/dev/chosen"), "/dev/chosen")

    def test_exclusive_port_is_released(self):
        device = Device()
        transcript = console.Transcript()
        serial = None
        try:
            serial = console.Serial(device.path, 115200, 0.5, transcript)
            # Some macOS PTYs permit a second raw open despite TIOCEXCL;
            # our advisory lock still prevents a second console owner.
            with self.assertRaises(OSError):
                console.Serial(device.path, 115200, 0.5, transcript)
            serial.close()
            other = os.open(device.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            os.close(other)
            self.assert_restored(device)
        finally:
            if serial:
                serial.close()
            device.close()


if __name__ == "__main__":
    unittest.main()
