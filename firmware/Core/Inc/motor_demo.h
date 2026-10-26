#ifndef MOTOR_DEMO_H
#define MOTOR_DEMO_H

#include <stdbool.h>
#include <stdint.h>

/* Visual command demonstrator only: no PWM, driver-enable, or motor output. */
typedef struct {
    bool enabled;
    bool led;
    uint8_t speed_pct;
    uint32_t last_toggle_ms;
    uint32_t blink_edges;
} MotorDemo;

void MotorDemo_Init(MotorDemo *demo);
void MotorDemo_Enable(MotorDemo *demo, bool enabled, uint32_t now);
bool MotorDemo_SetSpeed(MotorDemo *demo, unsigned speed, uint32_t now);
void MotorDemo_Update(MotorDemo *demo, uint32_t now);
uint32_t MotorDemo_PeriodMs(const MotorDemo *demo);

#endif
