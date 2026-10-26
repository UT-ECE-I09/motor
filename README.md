# Motor controller — UART command and LED simulation demo

One STM32G474RE firmware project for the NUCLEO-G474RE, with a laptop command console and a repeatable communication demo. The firmware uses the onboard ST-LINK Virtual COM Port over the board's USB cable. No separate UART adapter or jumper wires are needed on a stock board.

This is the senior design communication risk-reduction milestone. A simulated motor accepts start/stop and speed commands; the green LED represents motion by blinking faster at higher speed settings. It establishes MCU programming, bidirectional UART commands, command validation, nonblocking output updates, status readback, and saved evidence. No actual motor, PWM, gate driver, or speed measurement is involved.

## Quick start on this Mac

The board has already been programmed; to use the interface, open Terminal and run:

```sh
cd /Users/rolandwang/Senior-Design/motor
make console
```

At the `motor> ` prompt, try:

```text
help
info
motor on
speed 25
speed 100
speed down
speed up
status
motor off
```

Pause between speed commands to watch the green LED (LD2). Exit the laptop console with Ctrl-C or Ctrl-D. The console uses local line editing: type a command and press Enter.

| Command | Effect |
| --- | --- |
| `motor on` | Start blinking at the stored speed setting (25% after reset) |
| `motor off` | Stop blinking and turn the LED off; retain the speed setting |
| `speed 0` through `speed 100` | Set the simulated speed percentage; 0 stops blinking |
| `speed up` / `speed down` | Increase/decrease by 10 percentage points, clamped to 0–100 |
| `status` | Show simulation mode, motor state, speed, blink period/count, uptime, LED and UART errors |
| `ping hello` / `echo hello` | Check bidirectional communication |

The LED completes one blink every 1.55 seconds at 25%, 1.10 seconds at 50%, 0.65 seconds at 75%, and 0.20 seconds at 100%. These are illustrative blink rates, not motor RPM or a PWM duty cycle. Changing the speed while off stores the setting without starting the simulation. A reset returns to off/25%. Closing the console leaves the simulation in its current state: use `motor off` before exiting when you want it stopped.

Manual `led on/off/toggle` commands remain available while the motor simulation is off. They are rejected while it is on so they cannot conflict with the blink indicator. Invalid speed values leave the current setting unchanged.

To rerun the automated demonstration and save a timestamped transcript:

```sh
make demo
```

The automated demo checks on/off, observed blink timing at 25% and 100%, speed limits, zero-speed stopping, rejected invalid commands, and UART reliability. It finishes with the simulated motor off and speed set to 25%. The transcript is written to `logs/uart-demo.log`. For a unique filename or a specific serial port:

```sh
python3 tools/uart_console.py --list
python3 tools/uart_console.py --port /dev/cu.usbmodem2103 --demo --log logs/class-demo.log
python3 tools/uart_console.py --command 'ping hello'
```

The port name can change when the USB socket changes. With one USB serial device connected, it is detected automatically; multiple candidates require `--port`. Close other serial monitors before opening the console.

## Build and program

Requirements: Python 3, Make, Arm GNU embedded GCC 11 or newer, and STM32CubeProgrammer. The tools already installed on this Mac are used automatically: the compiler bundled with STM32CubeIDE and the STM32CubeProgrammer CLI. No Python packages, network downloads, or LHRE checkout are required to build and run this repository.

```sh
make          # produces firmware/build/motor_uart.elf, .bin, .hex and .map
make flash    # rebuilds, programs, verifies flash, then resets the board
make console
```

The flash helper checks for a NUCLEO-G474RE and device ID `0x469`. With multiple ST-LINK probes, select one explicitly:

```sh
python3 tools/flash.py --serial YOUR_STLINK_SERIAL
```

`make probe` resets and identifies the board without programming it. Programming uses SWD through ST-LINK at 1 MHz with connect-under-reset, which proved reliable on this board. This is separate from the UART data connection, although both use the same USB cable.

On other systems, put `arm-none-eabi-gcc` and `STM32_Programmer_CLI` on PATH, or use the build's `GCC_PATH` override and the `STM32_PROGRAMMER` environment variable. The laptop console supports macOS/Linux (POSIX serial ports); it is not a Windows console implementation.

## Hardware configuration

| Function | STM32 pin / setting |
| --- | --- |
| MCU | STM32G474RET6, Cortex-M4F, 512 KB flash |
| System clock | Internal HSI, 16 MHz; no external crystal dependency |
| UART | LPUART1, 115200 baud, 8 data bits, no parity, 1 stop bit, no flow control |
| MCU transmit | PA2, alternate function AF12, to ST-LINK VCP receive |
| MCU receive | PA3, alternate function AF12, from ST-LINK VCP transmit |
| User LED LD2 | PA5, active high |
| Debug | PA13/PA14 remain available for SWD |
| RAM allocation | 96 KB SRAM1 + SRAM2; 32 KB CCM is not allocated by this linker script |

According to [ST UM2505, sections 7.6–7.7](https://www.st.com/resource/en/user_manual/dm00556337-stm32g4-nucleo64-boards-mb1367-stmicroelectronics.pdf), PA2/PA3 connect to the ST-LINK VCP by default through SB17/SB23. Arduino D1/D0 can use different routing; do not assume those headers expose this UART in the factory configuration. Use the ST-LINK USB connector for this demo.

For a future custom PCB, this firmware's debug signals are 3.3 V logic. Route MCU TX to adapter RX, MCU RX to adapter TX, and connect ground. The USB-to-UART bridge currently resides on the Nucleo's ST-LINK section; this demo does not implement a native USB device on the G474.

## Project layout and LHRE reference

- `firmware/Core/Inc`, `firmware/Core/Src`: application, HAL setup, UART interrupt handling and command parser.
- `firmware/Core/Src/motor_demo.c`: portable simulation state and nonblocking LED timing, tested with a controlled clock including counter wraparound.
- `firmware/Drivers`: vendored ST HAL/CMSIS dependencies with upstream licenses.
- `firmware/startup_stm32g474xx.s`, `firmware/STM32G474RETX_FLASH.ld`: startup and memory layout.
- `tools/uart_console.py`: interactive console, single-command scripting, automated demo, transcript capture.
- `tools/flash.py`: board identification and verified programming.
- `docs/`: risk-reduction explanation and verification evidence.

The layout and HAL initialization follow `/Users/rolandwang/LHRE/LHRE Software/lhre-2026`, particularly `USM/firmware/Core/Src/usart.c` and its GCC build conventions. The ST drivers and startup files are copied locally so this project is independent. LHRE's USART1 PA9/PA10 mapping is replaced by the Nucleo's LPUART1 PA2/PA3 mapping. FreeRTOS and unrelated LHRE peripherals are omitted. This is a hand-maintained HAL/Make project; there is no CubeMX `.ioc` regeneration workflow.

## Protocol and limitations

Commands are ASCII, terminated by CR, LF, or CRLF. Responses end in `motor> `. Echo replies begin with `ECHO ` to distinguish payload text from that prompt. Send one command and wait for its prompt before sending the next. Maximum command length is 127 characters, excluding the newline. Oversized or invalid lines are rejected; the next complete command can be accepted. Interrupt-driven reception buffers incoming bytes while responses are transmitted.

This is a request/response debug console, not a real-time motor-control protocol. `status` reports software-observed state, not measured motor or gate-driver telemetry. Uptime is a 32-bit millisecond counter and wraps after about 49.7 days. The firmware does not configure motor outputs; a future power stage requires explicit hardware-safe enable defaults and communication-loss behavior.

If there is no response, confirm the ST-LINK USB cable is connected, run `--list`, close other serial programs, and run `make flash`. After an unplug or reset during a command, reconnect the console. If using a modified board, check the VCP solder bridges against UM2505.

Run host and firmware state-machine checks with `make test` (the latter also needs a native C compiler, such as Apple's command-line tools). Current hardware evidence is recorded in [motor simulation verification](docs/motor-simulation-verification.md); [original UART bring-up evidence](docs/verification.md) is preserved separately.
