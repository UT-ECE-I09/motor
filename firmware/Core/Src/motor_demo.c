#include "motor_demo.h"

void MotorDemo_Init(MotorDemo *demo)
{
    *demo = (MotorDemo){.speed_pct = 25};
}

void MotorDemo_Enable(MotorDemo *demo, bool enabled, uint32_t now)
{
    demo->enabled = enabled;
    demo->led = enabled && demo->speed_pct > 0;
    demo->last_toggle_ms = now;
}

bool MotorDemo_SetSpeed(MotorDemo *demo, unsigned speed, uint32_t now)
{
    if (speed > 100) return false;
    demo->speed_pct = (uint8_t)speed;
    demo->led = demo->enabled && speed > 0;
    demo->last_toggle_ms = now;
    return true;
}

uint32_t MotorDemo_PeriodMs(const MotorDemo *demo)
{
    return demo->enabled && demo->speed_pct ? 2000U - 18U * demo->speed_pct : 0U;
}

void MotorDemo_Update(MotorDemo *demo, uint32_t now)
{
    uint32_t period = MotorDemo_PeriodMs(demo);
    if (!period) return;
    if ((uint32_t)(now - demo->last_toggle_ms) >= period / 2U) {
        demo->led = !demo->led;
        ++demo->blink_edges;
        /* Non-blocking; count actual updates, not hypothetical missed edges. */
        demo->last_toggle_ms = now;
    }
}
