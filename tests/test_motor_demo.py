"""Run the actual portable firmware state machine against a controlled clock."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MotorStateTests(unittest.TestCase):
    def test_state_timing_limits_and_clock_wrap(self):
        compiler = shutil.which("cc")
        if not compiler:
            self.skipTest("A native C compiler is required for firmware state tests")
        source = r'''
#include "motor_demo.h"
#include <assert.h>
#include <stdint.h>
int main(void) {
    MotorDemo m;
    MotorDemo_Init(&m);
    assert(!m.enabled && !m.led && m.speed_pct == 25);
    assert(MotorDemo_PeriodMs(&m) == 0);
    MotorDemo_Update(&m, 10000);
    assert(m.blink_edges == 0);
    MotorDemo_Enable(&m, true, 10000);
    assert(m.led && MotorDemo_PeriodMs(&m) == 1550);
    MotorDemo_Update(&m, 10774);
    assert(m.led && m.blink_edges == 0);
    MotorDemo_Update(&m, 10775);
    assert(!m.led && m.blink_edges == 1);
    MotorDemo_Update(&m, 11550);
    assert(m.led && m.blink_edges == 2);
    assert(!MotorDemo_SetSpeed(&m, 101, 12000));
    assert(m.speed_pct == 25 && m.last_toggle_ms == 11550);
    assert(MotorDemo_SetSpeed(&m, 100, UINT32_MAX - 49));
    assert(MotorDemo_PeriodMs(&m) == 200);
    MotorDemo_Update(&m, 49);
    assert(m.led && m.blink_edges == 2);
    MotorDemo_Update(&m, 50);
    assert(!m.led && m.blink_edges == 3);
    MotorDemo_SetSpeed(&m, 0, 100);
    MotorDemo_Update(&m, 100000);
    assert(m.enabled && !m.led && m.blink_edges == 3);
    assert(MotorDemo_PeriodMs(&m) == 0);
    MotorDemo_SetSpeed(&m, 75, 100000);
    assert(m.led && MotorDemo_PeriodMs(&m) == 650);
    MotorDemo_Enable(&m, false, 100001);
    MotorDemo_Update(&m, 200000);
    assert(!m.led && m.speed_pct == 75 && m.blink_edges == 3);
    MotorDemo_SetSpeed(&m, 50, 200000);
    assert(!m.enabled && !m.led);
    MotorDemo_Enable(&m, true, 200000);
    assert(m.led && MotorDemo_PeriodMs(&m) == 1100);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "test.c").write_text(source)
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT / "firmware/Core/Inc"),
                            str(ROOT / "firmware/Core/Src/motor_demo.c"),
                            str(path / "test.c"), "-o", str(path / "test")], check=True)
            subprocess.run([str(path / "test")], check=True)
