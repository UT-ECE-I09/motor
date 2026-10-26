#!/usr/bin/env python3
"""Program and verify the UART demo using the Nucleo's onboard ST-LINK."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MAC_CLI = Path('/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/Resources/bin/STM32_Programmer_CLI')


def run(cli, *args):
    result = subprocess.run([str(cli), *map(str, args)], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)
    print(output, end='')
    if result.returncode or re.search(r'\bError:', output, re.I):
        raise RuntimeError('STM32CubeProgrammer failed; see output above.')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', help='ST-LINK serial number (required if multiple probes are attached)')
    parser.add_argument('--probe', action='store_true', help='Reset and identify MCU without programming it')
    parser.add_argument('--image', type=Path, help='ELF image; defaults to firmware/build/motor_uart.elf')
    args = parser.parse_args()
    cli = os.environ.get('STM32_PROGRAMMER') or shutil.which('STM32_Programmer_CLI')
    if not cli and MAC_CLI.is_file():
        cli = MAC_CLI
    if not cli:
        raise RuntimeError('Install STM32CubeProgrammer or set STM32_PROGRAMMER to its CLI path.')
    listing = run(cli, '-l', 'stlink')
    serials = re.findall(r'ST-LINK SN\s*:\s*(\S+)', listing)
    serial = args.serial
    if serial and serial not in serials:
        raise RuntimeError(f'Requested probe {serial} is not connected.')
    if not serial:
        if len(serials) != 1:
            raise RuntimeError(f'Found {len(serials)} probes; connect one or specify --serial.')
        serial = serials[0]
    connection = ['-c', 'port=SWD', f'sn={serial}', 'mode=UR', 'reset=HWrst', 'freq=1000']
    identity = run(cli, *connection)
    if not re.search(r'Board\s*:\s*NUCLEO-G474RE\b', identity):
        raise RuntimeError('Expected NUCLEO-G474RE; refusing to program a different board.')
    if not re.search(r'Device ID\s*:\s*0x469\b', identity, re.I):
        raise RuntimeError('Unexpected MCU device ID; refusing to program.')
    if args.probe:
        return
    image = args.image or ROOT / 'firmware/build/motor_uart.elf'
    if not image.is_file():
        raise RuntimeError(f'Missing {image}; run make first.')
    run(cli, *connection, '-w', image.resolve(), '-v', '-rst')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
