# UART risk-reduction verification — October 26, 2026

**Result: passed on the connected physical NUCLEO-G474RE.**

This test demonstrates the ability to build and flash STM32G474 firmware and exchange commands and responses between the MCU and a laptop through the Nucleo's ST-LINK USB serial bridge.

## Hardware and software observed

- NUCLEO-G474RE, ST-LINK serial `003B00313234511137333934`, firmware `V3J9M3`.
- Target device ID `0x469`, revision X, 512 KB flash, reported target supply 3.30 V.
- MCU UID returned by the application: `004A001D4843500620323556`.
- macOS serial port `/dev/cu.usbmodem2103`; LPUART1 PA2 TX / PA3 RX, 115200 8N1.
- Application reports `sysclk_hz=16000000` from internal HSI.
- Built with CubeIDE's Arm GNU GCC 14.3.1 and programmed with STM32CubeProgrammer 2.23.0.
- Linker allocation: 15,460 bytes flash; 4,720 bytes SRAM including reserved heap and stack.

## Completed checks

| Check | Observed result |
| --- | --- |
| Firmware build | Successful, no compiler/linker warnings |
| Program flash and readback verification | CubeProgrammer reported `Download verified successfully` |
| Identity command | Correct board, MCU, UART, baud, clock, and unique device identifier |
| Bidirectional ping | Unique token returned exactly |
| Repeated communication | 100/100 unique ping responses in 0.494 seconds |
| GPIO command | `led on` and `led off` acknowledged; following status reflected each state |
| Echo | Laptop payload returned with `ECHO` prefix |
| Invalid command | Rejected with `ERR unknown command` |
| Oversized input | 512-byte line rejected with `ERR line too long (max 127)` |
| Recovery | Next unique ping returned correctly |
| Final status | LED off, `rx_errors=0` |
| Host regression tests | Seven PTY-based tests passed, including framing, timeout, exclusive port ownership, log creation, and cleanup |

The complete timestamped serial transcript is [uart-demo-2026-10-26.log](uart-demo-2026-10-26.log). Timestamps in the transcript are UTC. This test ran at approximately 12:39 p.m. America/Chicago. LED state was verified through firmware readback; visual illumination was not independently observed.

Tested firmware binary SHA-256: `c89c93829b516a681aa319738428b20723ec2e26cdeb31fb038736cb85a19c1f`.

The original 512 KB flash contents were saved locally in `logs/nucleo-original-flash.bin` before programming. This backup is ignored by Git. No option bytes or ST-LINK firmware were modified. A transient ST-LINK USB timeout occurred during enumeration; a retry succeeded. Connect-under-reset at 1 MHz was used for reliable target access.

## Reproduce for class

1. Connect the Nucleo's ST-LINK USB port to the laptop.
2. From the repository, run `make flash` if rebuilding is needed.
3. Run `make console`; enter `info`, `ping senior-design`, `led on`, `status`, `led off`.
4. Exit with Ctrl-D, then run `make demo` to generate your own transcript.
5. Show the board, console responses, and saved log together.

## Requirement connection and remaining work

[I09 Project Definition, October 16, 2026](https://docs.google.com/document/d/1GKYqPQOYMOsruw__04vlRMEvL6cLfg3tIQWecUuwkA8/edit), sections 2.7.1–2.7.2, calls for a USB serial interface, command/script access, status reporting, saved logs, firmware flashing, and setup instructions. This prototype addresses the foundational interface and bring-up risks for those requirements.

It does not establish motor operation, measured motor telemetry, native USB on a custom PCB, closed-loop timing, or communication-loss shutdown of a power stage. Requirement P14's eight timestamped channels at at least 1 kHz for 60 seconds has not been tested. At 115200 baud with 8N1 framing, the serial wire carries at most 11,520 payload bytes per second before protocol overhead, so that future requirement needs a separate bandwidth and protocol design. `status` currently reports uptime, LED state, and a communication error counter only.

Pin routing is based on [ST UM2505, rev. 7, sections 7.6–7.7](https://www.st.com/resource/en/user_manual/dm00556337-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf), and the HAL/build structure follows the user's LHRE 2026 firmware. See [firmware provenance](../firmware/PROVENANCE.md).
