#!/usr/bin/env python3
"""Run the simulated MCU -> bridge -> WebSocket client chain across baud rates and sample
rates, and print a results table. A headless client stands in for the browser."""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame
from bridge import ws_frame, ws_read

HERE = os.path.dirname(os.path.abspath(__file__))
DURATION = 8
CASES = [(baud, rate) for baud in (115200, 921600) for rate in (50, 100, 200)]


async def client(port, seconds):
    for _ in range(50):
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            break
        except OSError:
            await asyncio.sleep(0.1)
    key = base64.b64encode(os.urandom(16))
    writer.write(b"GET /ws HTTP/1.1\r\nHost: x\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                 b"Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: " + key + b"\r\n\r\n")
    await reader.readuntil(b"\r\n\r\n")
    frames = 0
    try:
        async with asyncio.timeout(seconds):
            while True:
                op, data = await ws_read(reader)
                if op == 2:
                    frames += 1
                    if frames % 10 == 0:
                        echo = int.from_bytes(data[:8], "little")
                        writer.write(ws_frame(1, json.dumps({"echo": echo}).encode(), mask=True))
    except (TimeoutError, asyncio.IncompleteReadError, ConnectionError):
        pass
    writer.close()
    return frames


async def run(baud, rate, port):
    with tempfile.NamedTemporaryFile(suffix=".json") as out:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, os.path.join(HERE, "bridge.py"), "--sim", "--baud", str(baud),
            "--rate", str(rate), "--http-port", str(port), "--duration", str(DURATION),
            "--summary", out.name, stdout=subprocess.DEVNULL)
        frames = await client(port, DURATION - 0.5)
        await proc.wait()
        s = json.load(open(out.name))
    load = rate * frame.WIRE_SIZE * 10 / baud
    lost = 100 * s["lost"] / max(1, s["lost"] + s["rx"])
    return (f"| {baud} | {rate} | {load:.0%} | {s['rx'] / DURATION:.0f} | {lost:.1f}% | {s['bad']} | "
            f"{s['lat_p50_ms']} / {s['lat_p99_ms']} | {s['rtt_p50_ms']} / {s['rtt_p99_ms']} | "
            f"{frames / (DURATION - 0.5):.0f} | {s['cpu_pct']}% |")


async def main():
    print(f"{frame.WIRE_SIZE}-byte frames, {DURATION} s per case\n")
    print("| Baud | Sample Hz | UART load | Rx Hz | Lost | CRC errors | Serial latency p50/p99 (ms) "
          "| WS RTT p50/p99 (ms) | Client Hz | Bridge CPU |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for i, (baud, rate) in enumerate(CASES):
        print(await run(baud, rate, 8100 + i), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
