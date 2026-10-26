# Motor command simulation — October 26, 2026

Firmware v1.1 was built, programmed with successful readback verification, and tested on the same connected NUCLEO-G474RE. The full serial record is [motor-simulation-2026-10-26.log](motor-simulation-2026-10-26.log).

The laptop sends motor enable and speed commands; the STM32 validates them, updates its simulated motor state, and changes the PA5 LED blink timing without blocking UART command handling. Replies identify the mode as `led_simulation`. No motor-control pins or power-stage outputs are configured.

## Results observed on the board

| Check | Result |
| --- | --- |
| `motor on`, speed 25% | Blink period reported as 1550 ms; two timer-driven LED toggles over 1722 ms |
| Speed 100% | Blink period reported as 200 ms; eight toggles over 821 ms |
| `speed down` / `speed up` | 100 → 90 → 100; additional up remains at 100 |
| Speed 0% | LED off; zero toggles over 267 ms; down remains at 0 |
| `motor off` at speed 100% | LED off; zero toggles over 268 ms; setting retained |
| Invalid speeds | `-1`, `101`, `fast`, and `50junk` rejected; setting unchanged |
| Manual LED command while enabled | Rejected to avoid conflict with simulation |
| UART regression | 100/100 unique ping replies; oversized-line rejection and recovery; zero UART errors |
| Final state | Motor off, speed 25%, LED off |

Blink evidence is the firmware's timer-driven LED toggle counter and status readback, not an independent optical measurement. The user can observe the board's green LED while issuing the same commands.

All nine automated tests passed: eight host serial/PTY tests (including a negative test that detects a nonblinking simulation), plus a native C test of the actual firmware state machine. The C test covers startup off, timing thresholds, on/off, zero speed, invalid values, retained settings, and millisecond-counter wraparound.

Build allocation: 16,588 bytes flash and 4,728 bytes SRAM including reserved heap/stack. Firmware binary SHA-256: `2b47b3b8a88561193cc7572d8245eaf17454ed0fe965d6a16c4e7e83d53c9530`.

## Class demonstration

Run `make console`, then enter each command separately, pausing to show the LED:

```text
motor on
speed 25
speed 100
speed down
status
motor off
```

Explain that this demonstrates the planned controller's command path: laptop request → UART reception → validated enable/speed state → visible hardware output → status returned to the laptop. The LED substitutes for the future motor power stage. Speed is a requested percentage, not measured RPM; real PWM, gate-driver hardware, feedback, and communication-loss shutdown remain future work. The demo retains its state when the console disconnects; reset starts it off.
