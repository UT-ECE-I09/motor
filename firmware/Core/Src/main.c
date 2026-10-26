#include "main.h"
#include "motor_demo.h"
#include <stdio.h>
#include <string.h>

/* Only PA2/PA3 (debug UART) and PA5 (Nucleo LED) are configured. */
UART_HandleTypeDef hlpuart1;
#define RX_RING_SIZE 1024U
#define MAX_LINE 127U
static volatile uint8_t rx_ring[RX_RING_SIZE];
static volatile uint32_t rx_head, rx_tail, rx_errors;
static volatile uint8_t rx_lost;
static uint8_t rx_byte;
static uint8_t led_on;
static MotorDemo motor;

static void send_text(const char *text)
{
    if (HAL_UART_Transmit(&hlpuart1, (const uint8_t *)text,
                          (uint16_t)strlen(text), 1000U) != HAL_OK) {
        ++rx_errors;
    }
}

static void set_led(uint8_t value)
{
    led_on = value;
    HAL_GPIO_WritePin(GPIOA, GPIO_PIN_5, value ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void execute(char *line)
{
    char reply[192];
    if (strcmp(line, "help") == 0) {
        send_text("MOTOR DEMO (LED simulation only; no real motor output)\r\n"
                  "motor on | motor off | speed 0..100 | speed up | speed down\r\n"
                  "status | help | info | ping [token] | echo TEXT\r\n"
                  "led on/off/toggle (manual test; motor must be off)\r\n");
    } else if (strcmp(line, "info") == 0) {
        (void)snprintf(reply, sizeof(reply),
            "board=NUCLEO-G474RE mcu=STM32G474RE uart=LPUART1 baud=115200 sysclk_hz=%lu uid=%08lX%08lX%08lX\r\n",
            (unsigned long)SystemCoreClock, (unsigned long)HAL_GetUIDw0(),
            (unsigned long)HAL_GetUIDw1(), (unsigned long)HAL_GetUIDw2());
        send_text(reply);
        send_text("firmware=1.1 mode=led_simulation\r\n");
    } else if (strcmp(line, "ping") == 0) {
        send_text("PONG\r\n");
    } else if (strncmp(line, "ping ", 5) == 0) {
        send_text("PONG "); send_text(line + 5); send_text("\r\n");
    } else if (strcmp(line, "status") == 0) {
        (void)snprintf(reply, sizeof(reply),
            "mode=led_simulation motor=%s speed_pct=%u blink_period_ms=%lu blink_edges=%lu uptime_ms=%lu led=%s rx_errors=%lu\r\n",
            motor.enabled ? "on" : "off", (unsigned)motor.speed_pct,
            (unsigned long)MotorDemo_PeriodMs(&motor), (unsigned long)motor.blink_edges,
            (unsigned long)HAL_GetTick(), led_on ? "on" : "off", (unsigned long)rx_errors);
        send_text(reply);
    } else if (strcmp(line, "motor on") == 0 || strcmp(line, "motor off") == 0) {
        MotorDemo_Enable(&motor, strcmp(line, "motor on") == 0, HAL_GetTick());
        set_led(motor.led);
        send_text(motor.enabled ? "OK motor=on mode=led_simulation\r\n" :
                                  "OK motor=off mode=led_simulation\r\n");
    } else if (strcmp(line, "speed") == 0 || strncmp(line, "speed ", 6) == 0) {
        unsigned speed = 0;
        if (strcmp(line, "speed up") == 0) {
            speed = motor.speed_pct > 90 ? 100 : motor.speed_pct + 10;
        } else if (strcmp(line, "speed down") == 0) {
            speed = motor.speed_pct < 10 ? 0 : motor.speed_pct - 10;
        } else {
            const char *value = line + (line[5] == ' ' ? 6 : 5);
            if (!*value) { send_text("ERR speed must be 0..100, up, or down\r\n"); return; }
            for (; *value; ++value) {
                if (*value < '0' || *value > '9') {
                    send_text("ERR speed must be 0..100, up, or down\r\n"); return;
                }
                speed = speed * 10U + (unsigned)(*value - '0');
                if (speed > 100) { send_text("ERR speed must be 0..100\r\n"); return; }
            }
        }
        (void)MotorDemo_SetSpeed(&motor, speed, HAL_GetTick());
        if (motor.enabled) set_led(motor.led);
        (void)snprintf(reply, sizeof(reply), "OK speed_pct=%u\r\n", speed);
        send_text(reply);
    } else if (strcmp(line, "led on") == 0 || strcmp(line, "led off") == 0 ||
               strcmp(line, "led toggle") == 0) {
        if (motor.enabled) { send_text("ERR motor simulation active; use motor off\r\n"); return; }
        if (strcmp(line, "led toggle") == 0) set_led(!led_on);
        else set_led(strcmp(line, "led on") == 0);
        send_text(led_on ? "OK led=on\r\n" : "OK led=off\r\n");
    } else if (strncmp(line, "echo ", 5) == 0) {
        send_text("ECHO "); send_text(line + 5); send_text("\r\n");
    } else if (strcmp(line, "echo") == 0) {
        send_text("ECHO\r\n");
    } else if (line[0] != '\0') {
        send_text("ERR unknown command\r\n");
    }
}

/* UART interrupt owns head; foreground owns tail. Publish each byte only after
 * storing it. Receive stays armed while foreground transmits a reply. */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *uart)
{
    if (uart != &hlpuart1) return;
    uint32_t next = (rx_head + 1U) % RX_RING_SIZE;
    if (next == rx_tail) { ++rx_errors; rx_lost = 1U; }
    else { rx_ring[rx_head] = rx_byte; __DMB(); rx_head = next; }
    if (HAL_UART_Receive_IT(uart, &rx_byte, 1U) != HAL_OK) {
        ++rx_errors; rx_lost = 1U;
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *uart)
{
    if (uart != &hlpuart1) return;
    ++rx_errors;
    rx_lost = 1U;
    /* No DMA is used. Abort clears receive state before rearming after ORE. */
    (void)HAL_UART_AbortReceive(uart);
    __HAL_UART_CLEAR_FLAG(uart, UART_CLEAR_OREF | UART_CLEAR_NEF |
                               UART_CLEAR_FEF | UART_CLEAR_PEF);
    if (HAL_UART_Receive_IT(uart, &rx_byte, 1U) != HAL_OK) ++rx_errors;
}

static void clock_init(void)
{
    RCC_OscInitTypeDef osc = {0};
    osc.OscillatorType = RCC_OSCILLATORTYPE_HSI;
    osc.HSIState = RCC_HSI_ON;
    osc.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
    osc.PLL.PLLState = RCC_PLL_NONE;
    if (HAL_RCC_OscConfig(&osc) != HAL_OK) Error_Handler();
    RCC_ClkInitTypeDef clock = {0};
    clock.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                      RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    clock.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
    clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
    clock.APB1CLKDivider = RCC_HCLK_DIV1;
    clock.APB2CLKDivider = RCC_HCLK_DIV1;
    if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_0) != HAL_OK) Error_Handler();
}

static void uart_init(void)
{
    hlpuart1.Instance = LPUART1;
    hlpuart1.Init.BaudRate = 115200;
    hlpuart1.Init.WordLength = UART_WORDLENGTH_8B;
    hlpuart1.Init.StopBits = UART_STOPBITS_1;
    hlpuart1.Init.Parity = UART_PARITY_NONE;
    hlpuart1.Init.Mode = UART_MODE_TX_RX;
    hlpuart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    hlpuart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
    hlpuart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
    hlpuart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
    if (HAL_UART_Init(&hlpuart1) != HAL_OK ||
        HAL_UARTEx_DisableFifoMode(&hlpuart1) != HAL_OK) Error_Handler();
    if (HAL_UART_Receive_IT(&hlpuart1, &rx_byte, 1U) != HAL_OK) Error_Handler();
}

int main(void)
{
    HAL_Init();
    clock_init();
    __HAL_RCC_GPIOA_CLK_ENABLE();
    GPIO_InitTypeDef led = {0};
    led.Pin = GPIO_PIN_5;
    led.Mode = GPIO_MODE_OUTPUT_PP;
    led.Pull = GPIO_NOPULL;
    led.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOA, &led);
    set_led(0);
    MotorDemo_Init(&motor);
    uart_init();
    send_text("\r\nMotor controller command demo v1.1 (LED simulation only)\r\n"
              "NUCLEO-G474RE | LPUART1 PA2 TX / PA3 RX | 115200 8N1\r\n"
              "Type help for commands.\r\nmotor> ");

    char line[MAX_LINE + 1U];
    uint32_t length = 0;
    uint8_t discard = 0, skip_lf = 0;
    for (;;) {
        MotorDemo_Update(&motor, HAL_GetTick());
        if (motor.enabled && led_on != motor.led) set_led(motor.led);
        if (rx_lost) {
            /* Discard every queued byte, then resynchronize at a future line
             * ending. Never execute a command assembled across lost data. */
            __disable_irq();
            rx_tail = rx_head;
            rx_lost = 0;
            __enable_irq();
            length = 0;
            discard = 2;
            skip_lf = 0;
        }
        if (rx_tail == rx_head) continue;
        uint8_t ch = rx_ring[rx_tail];
        __DMB();
        rx_tail = (rx_tail + 1U) % RX_RING_SIZE;
        if (skip_lf && ch == '\n') { skip_lf = 0; continue; }
        skip_lf = 0;
        if (ch == '\r' || ch == '\n') {
            skip_lf = (ch == '\r');
            if (discard == 1) send_text("ERR line too long (max 127)\r\n");
            else if (discard == 2) send_text("ERR receive overflow or UART error\r\n");
            else if (discard == 3) send_text("ERR non-printable input\r\n");
            else { line[length] = '\0'; execute(line); }
            length = 0;
            discard = 0;
            send_text("motor> ");
        } else if (discard) {
            continue;
        } else if (ch == 8U || ch == 127U) {
            if (length) --length;
        } else if (ch < 32U || ch > 126U) {
            discard = 3;
        } else if (length == MAX_LINE) {
            discard = 1;
        } else {
            line[length++] = (char)ch;
        }
    }
}

void Error_Handler(void)
{
    __disable_irq();
    while (1) { /* Attach debugger to inspect a failed initialization. */ }
}
