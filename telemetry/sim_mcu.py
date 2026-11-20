#!/usr/bin/env python3
"""Stand-in for the main control board MCU: streams 9-joint telemetry over a serial fd.

Bytes are paced at the UART baud rate (8N1, 10 bits/byte). Like a DMA UART with no
queue, a sample is dropped if the previous frame is still being transmitted.
"""
import argparse
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import frame


def joints_at(t):
    out = []
    for i in range(9):
        if i == 8:  # head pan: slow sweep
            pos = 0.6 * math.sin(2 * math.pi * 0.1 * t)
            vel = 0.6 * 2 * math.pi * 0.1 * math.cos(2 * math.pi * 0.1 * t)
        else:  # legs: 1 Hz gait, right leg half a cycle behind
            amp = [0.05, 0.35, 0.4, 0.2][i % 4]
            w = 2 * math.pi * 1.0
            ph = w * t + (math.pi if i >= 4 else 0) + (i % 4) * 0.4
            pos, vel = amp * math.sin(ph), amp * w * math.cos(ph)
        out.append((pos, vel, 0.3 + 0.8 * abs(vel) + random.gauss(0, 0.02)))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fd", type=int, required=True, help="serial file descriptor to write to")
    p.add_argument("--rate", type=float, default=100, help="sample rate, Hz")
    p.add_argument("--baud", type=int, default=921600)
    args = p.parse_args()

    period, byte_time = 1 / args.rate, 10 / args.baud
    t0 = time.monotonic()
    link_free = t0
    seq = k = 0
    while True:
        tick = t0 + k * period
        k += 1
        delay = tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        if tick < link_free:  # UART still busy with the previous frame
            seq += 1
            continue
        wire = frame.encode(frame.pack(seq, time.time_ns() // 1000, joints_at(tick - t0)))
        seq += 1
        link_free = max(time.monotonic(), tick) + len(wire) * byte_time
        delay = link_free - time.monotonic()
        if delay > 0:
            time.sleep(delay)  # last byte arrives at the receiver after the wire time
        os.write(args.fd, wire)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError, OSError):
        pass
