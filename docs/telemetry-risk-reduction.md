# Individual Risk Reduction: Joint Telemetry to the Browser Dashboard

**Team:** I09 | **Student:** Anish Yande (non-control software: dashboard, video, wireless link) | **Date:** November 20, 2026

## Risk

The dashboard needs live joint state from the robot. That data takes this path: main control board MCU → UART → Raspberry Pi → Wi-Fi → browser. If any link can't keep up at the control rate, the operator sees stale or missing data, and the team only finds out during integration. The bus, message format and update rate are still open interfaces in the design doc.

## Activity

I built a minimal version of the full chain and measured it. The code is in `telemetry/` and uses only the Python standard library, so it runs unchanged on a Pi.

- **Frame format** (`frame.py`): sequence number, MCU timestamp, and 9 joints × (position, velocity, current). The frames carry a CRC-16 and are COBS-framed, so each frame is 124 bytes on the wire. A gap in the sequence number counts lost frames, and the CRC rejects corrupted ones.
- **MCU stand-in** (`sim_mcu.py`): generates a 1 Hz walking gait and writes it to a serial port, paced at the real UART byte rate. If the line is still busy with the previous frame, it drops the new one, the way a DMA UART with no queue would.
- **Bridge** (`bridge.py`, the Pi software): reads the serial port, checks each frame, and forwards it to browsers over WebSocket. It reports rate, losses, serial latency, browser round-trip time and CPU once a second. It also skips frames for a browser that falls behind instead of blocking.
- **Dashboard** (`dashboard.html`): a joint table and a position plot, plus the stats line.

To run it: `python3 telemetry/bridge.py --sim`, then open http://localhost:8080. To run the measurements: `python3 telemetry/bench.py`.

## Results (laptop, simulated MCU over a pseudo-terminal, 8 s per case)

| Baud | Sample Hz | UART load | Rx Hz | Lost | Serial latency p50/p99 | WS RTT p99 | Bridge CPU |
|---|---|---|---|---|---|---|---|
| 115200 | 50 | 54% | 50 | 0% | 13.5 / 13.7 ms | 0.5 ms | 0.5% |
| 115200 | 100 | 108% | 50 | 49.9% | 13.5 / 13.6 ms | 0.5 ms | 0.4% |
| 115200 | 200 | 215% | 66 | 66.6% | 13.5 / 13.6 ms | 0.7 ms | 0.5% |
| 921600 | 50 | 7% | 50 | 0% | 2.0 / 4.7 ms | 1.6 ms | 1.4% |
| 921600 | 100 | 13% | 100 | 0% | 2.0 / 2.6 ms | 1.1 ms | 2.4% |
| 921600 | 200 | 27% | 199 | 0.2% | 1.9 / 2.2 ms | 0.9 ms | 3.8% |

No CRC errors occurred in any case, and the headless browser client received every frame the bridge forwarded.

## Findings

1. **115200 baud cannot carry full joint state at 100 Hz.** It tops out at about 93 frames/s, and in practice half the frames are lost. That baud rate is the one our current Nucleo UART demo uses. The robot link needs at least 921600 baud (13% load at 100 Hz), or a faster bus.
2. **At 921600 baud the chain is fast and cheap.** Serial latency is about 2 ms, and the bridge's own share is small: on a laptop it uses under 4% CPU at 200 Hz. That leaves headroom for the policy and video on the Pi.
3. **Sequence numbers and CRC catch problems quickly.** Lost and corrupted frames show up on the dashboard within a second, which will help during hardware bring-up.

## Remaining checks

- Run `bench.py` on the actual Pi (CM4/CM5). Laptop CPU numbers understate the Pi's load.
- Repeat over real Wi-Fi with a phone or laptop browser, and on a real UART from the Nucleo at 921600 baud.
- Agree on the frame fields with Roland (firmware) and Naman (control board) before firmware work starts.
