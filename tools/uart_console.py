#!/usr/bin/env python3
"""NUCLEO UART console and repeatable risk-reduction check; Python stdlib only."""

import argparse
import datetime
import fcntl
import glob
import os
from pathlib import Path
import re
import select
import sys
import termios
import time
import uuid

PROMPT = b"motor> "


class ConsoleError(Exception):
    pass


def ports():
    patterns = ("/dev/cu.usbmodem*",) if sys.platform == "darwin" else (
        "/dev/ttyACM*", "/dev/ttyUSB*"
    )
    return sorted({p for pattern in patterns for p in glob.glob(pattern)})


def choose_port(explicit):
    if explicit:
        return explicit
    found = ports()
    if not found:
        raise ConsoleError("No UART port found. Connect the Nucleo ST-LINK USB port or use --port.")
    if len(found) != 1:
        raise ConsoleError("Multiple UART ports found; choose --port: " + ", ".join(found))
    return found[0]


class Transcript:
    def __init__(self, path=None):
        self.file = None
        if path:
            destination = Path(path).expanduser()
            destination.parent.mkdir(parents=True, exist_ok=True)
            self.file = destination.open("a", encoding="utf-8", buffering=1)

    def record(self, direction, message):
        if self.file:
            stamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
            # One timestamp per physical line; preserve content including empty replies.
            for line in str(message).replace("\r", "").split("\n"):
                self.file.write(f"{stamp} {direction} {line}\n")

    def close(self):
        if self.file:
            self.file.close()


class Serial:
    def __init__(self, port, baud, timeout, transcript):
        self.fd = None
        self.saved = None
        self.exclusive = False
        self.buffer = bytearray()
        self.timeout = timeout
        self.log = transcript
        speed = getattr(termios, "B" + str(baud), None)
        if speed is None:
            raise ConsoleError(f"Unsupported baud rate: {baud}")
        try:
            self.fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if hasattr(termios, "TIOCEXCL"):
                fcntl.ioctl(self.fd, termios.TIOCEXCL)
                self.exclusive = True
            self.saved = termios.tcgetattr(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attrs[3] = 0
            attrs[4] = speed
            attrs[5] = speed
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            self.log.record("SESSION", f"port={port} baud={baud} 8N1 flow_control=none")
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.fd is None:
            return
        try:
            if self.saved is not None:
                try:
                    termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)
                except OSError:
                    pass  # A disconnected device cannot accept restored settings.
            if self.exclusive and hasattr(termios, "TIOCNXCL"):
                try:
                    fcntl.ioctl(self.fd, termios.TIOCNXCL)
                except OSError:
                    pass
        finally:
            os.close(self.fd)
            self.fd = None

    def _read(self):
        try:
            data = os.read(self.fd, 4096)
        except BlockingIOError:
            return b""
        except OSError as exc:
            raise ConsoleError(f"UART disconnected or unreadable: {exc}") from exc
        if not data:
            raise ConsoleError("UART disconnected (end of stream)")
        return data

    def _write(self, data):
        deadline = time.monotonic() + self.timeout
        remaining = memoryview(data)
        while remaining:
            delay = deadline - time.monotonic()
            if delay <= 0 or not select.select([], [self.fd], [], max(0, delay))[1]:
                raise ConsoleError("Timed out writing UART command")
            try:
                remaining = remaining[os.write(self.fd, remaining):]
            except BlockingIOError:
                continue

    def _reply(self):
        deadline = time.monotonic() + self.timeout
        while True:
            # A prompt occurs at start or after a line break, never inside an echo.
            idx = self.buffer.find(PROMPT)
            while idx >= 0:
                if idx == 0 or self.buffer[idx - 1] in (10, 13):
                    data = bytes(self.buffer[:idx])
                    del self.buffer[:idx + len(PROMPT)]
                    reply = data.decode("utf-8", errors="replace").replace("\r", "").strip("\n")
                    self.log.record("RX", reply)
                    return reply
                idx = self.buffer.find(PROMPT, idx + 1)
            delay = deadline - time.monotonic()
            if delay <= 0 or not select.select([self.fd], [], [], max(0, delay))[0]:
                partial = bytes(self.buffer).decode("utf-8", errors="replace")
                self.log.record("RX PARTIAL", partial)
                raise ConsoleError(f"Timed out waiting for {PROMPT.decode()!r}; partial reply: {partial!r}")
            self.buffer.extend(self._read())
            if len(self.buffer) > 65536:
                raise ConsoleError("UART reply exceeded 64 KiB without a prompt")

    def synchronize(self):
        # Drain any boot banner / stale command response until a quiet interval.
        deadline = time.monotonic() + self.timeout
        startup = bytearray()
        while time.monotonic() < deadline:
            if not select.select([self.fd], [], [], min(0.15, max(0, deadline - time.monotonic())))[0]:
                break
            startup.extend(self._read())
            if len(startup) > 65536:
                raise ConsoleError("UART is streaming continuously; cannot synchronize")
        if startup:
            self.log.record("STARTUP", startup.decode("utf-8", errors="replace"))
        self.buffer.clear()
        self.command("")

    def command(self, command):
        if "\r" in command or "\n" in command:
            raise ConsoleError("Each command must be one line")
        self.log.record("TX", command)
        self._write(command.encode("utf-8") + b"\n")
        return self._reply()


def require(condition, message):
    if not condition:
        raise ConsoleError("Demo failed: " + message)


def run_motor_demo(exchange, log):
    """Verify command semantics and observed timer edges, without a motor stage."""
    def motor(state):
        require(exchange("motor " + state) == "OK motor=" + state + " mode=led_simulation",
                "motor acknowledgement mismatch")

    def speed(value, expected):
        require(exchange("speed " + str(value)) == "OK speed_pct=" + str(expected),
                "speed acknowledgement mismatch")

    def status(state, percent):
        raw = exchange("status")
        fields = dict(re.findall(r"\b([a-z_]+)=([^\s]+)", raw))
        period = 2000 - 18 * percent if state == "on" and percent else 0
        require(fields.get("mode") == "led_simulation" and fields.get("motor") == state
                and fields.get("speed_pct") == str(percent)
                and fields.get("blink_period_ms") == str(period)
                and fields.get("rx_errors") == "0", "invalid motor status: " + repr(raw))
        require(all(fields.get(key, "").isdigit() for key in ("blink_edges", "uptime_ms")),
                "missing motor timing counters")
        require(fields.get("led") in ("on", "off"), "missing LED state")
        if not period:
            require(fields["led"] == "off", "disabled simulation LED is not off")
        return fields

    def sample(state, percent, duration):
        before = status(state, percent)
        time.sleep(duration)
        after = status(state, percent)
        edges = (int(after["blink_edges"]) - int(before["blink_edges"])) & 0xffffffff
        elapsed = (int(after["uptime_ms"]) - int(before["uptime_ms"])) & 0xffffffff
        require(elapsed > 0, "uptime counter did not advance")
        result = f"motor={state} speed_pct={percent} elapsed_ms={elapsed} observed_blink_edges={edges}"
        log.record("MEASURE", result)
        print("MEASURE: " + result, flush=True)
        return edges, edges * 1000 / elapsed

    motor("off")
    speed(25, 25)
    motor("on")
    require(exchange("led on").startswith("ERR motor simulation active"),
            "manual LED command was accepted during motor simulation")
    low_edges, low_rate = sample("on", 25, 1.7)
    require(low_edges >= 1 and 0.5 <= low_rate <= 2.5, "25% speed blink rate incorrect")
    speed(100, 100)
    high_edges, high_rate = sample("on", 100, 0.8)
    require(high_edges >= 5 and 6 <= high_rate <= 14 and high_rate > 2 * low_rate,
            "100% speed did not produce the expected faster blinking")
    speed("down", 90)
    status("on", 90)
    speed("up", 100)
    speed("up", 100)  # Upper boundary clamps.
    speed(0, 0)
    speed("down", 0)  # Lower boundary clamps.
    require(sample("on", 0, 0.25)[0] == 0, "zero speed continued blinking")
    for invalid in ("-1", "101", "fast", "50junk"):
        require(exchange("speed " + invalid).startswith("ERR speed"),
                "invalid speed was accepted: " + invalid)
        status("on", 0)
    speed(100, 100)
    motor("off")
    require(sample("off", 100, 0.25)[0] == 0, "motor off continued blinking")
    speed(25, 25)
    status("off", 25)
    result = "PASS: LED motor simulation on/off, measured speed change, speed limits, zero-speed stop, invalid input"
    log.record("RESULT", result)
    print(result, flush=True)


def run_demo(serial):
    def exchange(command):
        reply = serial.command(command)
        print(f"> {command if len(command) < 160 else '[512-byte oversized line]'}\n{reply}", flush=True)
        return reply

    nonce = uuid.uuid4().hex[:12]
    info = exchange("info")
    require("board=NUCLEO-G474RE" in info and "mcu=STM32G474RE" in info,
            "unexpected firmware identity: " + repr(info))
    require(exchange("ping " + nonce).splitlines() == ["PONG " + nonce], "initial ping mismatch")
    run_motor_demo(exchange, serial.log)
    for state in ("on", "off"):
        require(exchange("led " + state).splitlines() == ["OK led=" + state], "LED acknowledgement mismatch")
        status = exchange("status")
        require(re.search(r"\buptime_ms=\d+\b", status) and re.search(r"\brx_errors=0\b", status)
                and re.search(r"\bled=" + state + r"\b", status), "invalid status: " + repr(status))
    payload = "laptop-to-stm32-" + nonce
    require(exchange("echo " + payload).splitlines() == ["ECHO " + payload], "echo mismatch")
    require(exchange("unknown_" + nonce).startswith("ERR unknown command"), "unknown command not rejected")
    started = time.monotonic()
    for i in range(100):
        token = f"{nonce}-{i:03d}"
        response = serial.command("ping " + token)
        require(response.splitlines() == ["PONG " + token], f"ping {i + 1}/100 mismatch: {response!r}")
    elapsed = time.monotonic() - started
    print(f"PASS: 100/100 distinct ping roundtrips in {elapsed:.3f} s", flush=True)
    require(exchange("x" * 512).startswith("ERR line too long"), "oversized line not rejected")
    recovery = nonce + "-recovery"
    require(exchange("ping " + recovery).splitlines() == ["PONG " + recovery], "no recovery after oversized line")
    final_status = exchange("status")
    require(re.search(r"\brx_errors=0\b", final_status) is not None, "UART receive errors after demo")
    result = "PASS: identity, motor LED simulation/speed, LED commands/status, echo, unknown command, 100 pings, oversized line rejection and recovery"
    serial.log.record("RESULT", result)
    print(result, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="serial device (auto-detects a single Nucleo VCP)")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=3.0, help="per-command timeout in seconds (default: 3)")
    parser.add_argument("--log", help="append a UTC timestamped transcript to this file")
    parser.add_argument("--list", action="store_true", help="list candidate serial ports and exit")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--command", help="send one command, print reply, and exit")
    mode.add_argument("--demo", action="store_true", help="run the repeatable hardware acceptance demo")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(ports()) or "No candidate UART ports found.")
        return 0
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    serial = None
    transcript = None
    try:
        transcript = Transcript(args.log)
        serial = Serial(choose_port(args.port), args.baud, args.timeout, transcript)
        serial.synchronize()
        if args.demo:
            run_demo(serial)
        elif args.command is not None:
            reply = serial.command(args.command)
            print(reply)
            if any(line.startswith("ERR") for line in reply.splitlines()):
                return 1
        else:
            print("Connected. Type help for commands; quit, Ctrl-D, or Ctrl-C to exit.")
            print("LED motor simulation: motor on | motor off | speed 25 | speed up | speed down | status")
            while True:
                try:
                    command = input("motor> ")
                except EOFError:
                    print()
                    break
                if command.strip() in ("quit", "exit"):
                    break
                print(serial.command(command))
        return 0
    except KeyboardInterrupt:
        print("\nDisconnected.", file=sys.stderr)
        return 130 if args.demo or args.command is not None else 0
    except (ConsoleError, OSError) as exc:
        if transcript:
            transcript.record("FAIL", str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        if serial:
            serial.close()
        if transcript:
            transcript.close()


if __name__ == "__main__":
    sys.exit(main())
