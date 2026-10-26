# STM32 source provenance

This hand-maintained HAL project follows the Core/Inc, Core/Src, GNU Arm startup,
linker, and Makefile conventions of Longhorn Racing Electric's lhre-2026.
It does not require CubeMX regeneration and has no .ioc file.

ST and Arm source files were copied from the user's local reference checkout:
`/Users/rolandwang/LHRE/LHRE Software/lhre-2026`.

- `Drivers/STM32G4xx_HAL_Driver`: headers and selected sources from
  `drivers/stm32g4/STM32G4xx_HAL_Driver`; HAL reports version 1.2.5.
- `Drivers/CMSIS/Include`: CMSIS core headers from `drivers/stm32g4/CMSIS/Include`.
- `Drivers/CMSIS/Device/ST/STM32G4xx`: G474 and family/system headers from the
  corresponding directory under `drivers/stm32g4`.
- `startup_stm32g474xx.s`: CMSIS device `Source/Templates/gcc` startup.
- `Core/Src/system_stm32g4xx.c`: CMSIS device `Source/Templates` system source.
- `STM32G474RETX_FLASH.ld`: adapted from `USM/firmware/STM32G474XX_FLASH.ld`;
  target description changed to RETx and contiguous SRAM allocation limited to
  96 KB at 0x20000000. The separate 32 KB CCM region is unused. Flash is 512 KB.

Original copyright headers and the component license files are retained under
Drivers. STM32 sources refer to their ST component license. CMSIS core headers
use the included Apache 2.0 license. Project-specific sources are newly written;
no LHRE motor-control/application code or FreeRTOS middleware is copied.

UART initialization follows the HAL sequence in `USM/firmware/Core/Src/usart.c`,
adapted from USART1 to the NUCLEO-G474RE ST-LINK virtual COM port: LPUART1,
PA2 TX / PA3 RX, alternate function 12, 115200 8N1. HSI16 supplies SYSCLK and
PCLK1. Only the debug UART and PA5 user LED are configured.
