#!/usr/bin/env python3
"""Raspberry Pi side: read MCU telemetry from serial, push it to browsers over WebSocket.

    python3 telemetry/bridge.py --sim --rate 100 --baud 921600   # laptop, simulated MCU
    python3 telemetry/bridge.py --port /dev/ttyAMA0 --baud 921600  # Pi, real MCU

Then open http://<host>:8080. Standard library only.

Browser message: u64 bridge send time (us) + raw 120-byte payload. Once a second the
bridge also sends a JSON stats message. Browsers echo send times back to measure RTT.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import pty
import struct
import subprocess
import sys
import termios
import time
import tty

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame

HERE = os.path.dirname(os.path.abspath(__file__))
WS_GUID = b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX_BUFFERED = 32 * 1024  # skip frames for a client that is this far behind


def now_us():
    return time.time_ns() // 1000


def ws_frame(opcode, payload, mask=False):
    head = bytearray([0x80 | opcode])
    n = len(payload)
    bit = 0x80 if mask else 0
    if n < 126:
        head.append(bit | n)
    elif n < 65536:
        head += bytes([bit | 126]) + struct.pack(">H", n)
    else:
        head += bytes([bit | 127]) + struct.pack(">Q", n)
    if mask:
        key = os.urandom(4)
        payload = bytes(b ^ key[i % 4] for i, b in enumerate(payload))
        head += key
    return bytes(head) + payload


async def ws_read(reader):
    b0, b1 = await reader.readexactly(2)
    n = b1 & 0x7F
    if n == 126:
        n, = struct.unpack(">H", await reader.readexactly(2))
    elif n == 127:
        n, = struct.unpack(">Q", await reader.readexactly(8))
    key = await reader.readexactly(4) if b1 & 0x80 else None
    data = await reader.readexactly(n)
    if key:
        data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
    return b0 & 0x0F, data


def pct(values, q):
    if not values:
        return None
    s = sorted(values)
    return round(s[min(len(s) - 1, int(q * len(s)))], 2)


class Bridge:
    def __init__(self):
        self.clients = set()
        self.buf = bytearray()
        self.last_seq = None
        self.total = dict(rx=0, lost=0, bad=0, ws_sent=0, ws_skipped=0)
        self.win_rx, self.win_lat, self.win_rtt = 0, [], []
        self.all_lat, self.all_rtt, self.cpu = [], [], []

    def on_serial(self, fd):
        self.buf += os.read(fd, 4096)
        *chunks, self.buf = self.buf.split(b"\0")
        for chunk in chunks:
            try:
                payload = frame.decode(bytes(chunk))
            except ValueError:
                self.total["bad"] += 1
                continue
            seq, t_us = frame.HEADER.unpack_from(payload)
            if self.last_seq is not None and seq > self.last_seq + 1:
                self.total["lost"] += seq - self.last_seq - 1
            self.last_seq = seq
            self.total["rx"] += 1
            self.win_rx += 1
            self.win_lat.append((now_us() - t_us) / 1000)  # valid when MCU clock = host clock (sim)
            self.broadcast(ws_frame(2, struct.pack("<Q", now_us()) + payload))

    def broadcast(self, msg):
        for w in list(self.clients):
            if w.transport.get_write_buffer_size() > MAX_BUFFERED:
                self.total["ws_skipped"] += 1
            else:
                w.write(msg)
                self.total["ws_sent"] += 1

    async def stats_loop(self):
        last_wall, last_cpu = time.monotonic(), time.process_time()
        while True:
            await asyncio.sleep(1)
            wall, cpu = time.monotonic(), time.process_time()
            cpu_pct = 100 * (cpu - last_cpu) / (wall - last_wall)
            last_wall, last_cpu = wall, cpu
            stats = dict(type="stats", rx_hz=self.win_rx, cpu_pct=round(cpu_pct, 1),
                         lat_p50_ms=pct(self.win_lat, .5), lat_p99_ms=pct(self.win_lat, .99),
                         rtt_p50_ms=pct(self.win_rtt, .5), rtt_p99_ms=pct(self.win_rtt, .99),
                         clients=len(self.clients), **self.total)
            self.all_lat += self.win_lat
            self.all_rtt += self.win_rtt
            self.cpu.append(cpu_pct)
            self.win_rx, self.win_lat, self.win_rtt = 0, [], []
            self.broadcast(ws_frame(1, json.dumps(stats).encode()))

    def summary(self):
        return dict(**self.total,
                    lat_p50_ms=pct(self.all_lat, .5), lat_p99_ms=pct(self.all_lat, .99),
                    lat_max_ms=pct(self.all_lat, 1), rtt_p50_ms=pct(self.all_rtt, .5),
                    rtt_p99_ms=pct(self.all_rtt, .99),
                    cpu_pct=round(sum(self.cpu) / len(self.cpu), 1) if self.cpu else None)

    async def handle_http(self, reader, writer):
        try:
            request = (await reader.readuntil(b"\r\n\r\n")).decode(errors="replace")
            path = request.split(" ", 2)[1]
            headers = {k.strip().lower(): v.strip() for k, _, v in
                       (line.partition(":") for line in request.split("\r\n")[1:]) if k}
            if path == "/ws" and "sec-websocket-key" in headers:
                accept = base64.b64encode(hashlib.sha1(headers["sec-websocket-key"].encode() + WS_GUID).digest())
                writer.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                             b"Connection: Upgrade\r\nSec-WebSocket-Accept: " + accept + b"\r\n\r\n")
                writer.write(ws_frame(1, json.dumps(dict(type="hello", joints=frame.JOINTS)).encode()))
                self.clients.add(writer)
                try:
                    while True:
                        op, data = await ws_read(reader)
                        if op == 8:
                            break
                        if op == 1:
                            echo = json.loads(data).get("echo")
                            if echo:
                                self.win_rtt.append((now_us() - echo) / 1000)
                finally:
                    self.clients.discard(writer)
            elif path == "/":
                with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                    body = f.read()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
            else:
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, IndexError, ValueError):
            pass
        finally:
            writer.close()


def open_serial(path, baud):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    tty.setraw(fd)
    speed = getattr(termios, f"B{baud}", None)
    if speed is not None:  # a pty ignores this; a real UART needs it
        attrs = termios.tcgetattr(fd)
        attrs[4] = attrs[5] = speed
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return fd


async def main():
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--port", help="serial device connected to the MCU")
    src.add_argument("--sim", action="store_true", help="spawn the simulated MCU on a pseudo-terminal")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--rate", type=float, default=100, help="simulated MCU sample rate, Hz")
    p.add_argument("--http-port", type=int, default=8080)
    p.add_argument("--duration", type=float, help="exit after this many seconds")
    p.add_argument("--summary", help="write a JSON summary here on exit")
    args = p.parse_args()

    sim = None
    if args.sim:
        master, slave = pty.openpty()
        tty.setraw(slave)
        fd = open_serial(os.ttyname(slave), args.baud)
        os.close(slave)
        sim = subprocess.Popen([sys.executable, os.path.join(HERE, "sim_mcu.py"), "--fd", str(master),
                                "--rate", str(args.rate), "--baud", str(args.baud)], pass_fds=(master,))
        os.close(master)
    else:
        fd = open_serial(args.port, args.baud)

    bridge = Bridge()
    loop = asyncio.get_running_loop()
    loop.add_reader(fd, bridge.on_serial, fd)
    server = await asyncio.start_server(bridge.handle_http, "0.0.0.0", args.http_port)
    print(f"dashboard: http://localhost:{args.http_port}", flush=True)
    stats = asyncio.create_task(bridge.stats_loop())
    try:
        await asyncio.sleep(args.duration if args.duration else float("inf"))
    finally:
        stats.cancel()
        server.close()
        if sim:
            sim.terminate()
        result = bridge.summary()
        print(json.dumps(result), flush=True)
        if args.summary:
            with open(args.summary, "w") as f:
                json.dump(result, f)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
