#include "main.h"
void SysTick_Handler(void) { HAL_IncTick(); }
void LPUART1_IRQHandler(void) { HAL_UART_IRQHandler(&hlpuart1); }
void NMI_Handler(void) { while (1) {} }
void HardFault_Handler(void) { while (1) {} }
void MemManage_Handler(void) { while (1) {} }
void BusFault_Handler(void) { while (1) {} }
void UsageFault_Handler(void) { while (1) {} }
