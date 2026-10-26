TARGET := motor_uart
BUILD_DIR := build
PREFIX ?= arm-none-eabi-
# Optional: make GCC_PATH=/path/to/bin. Otherwise use PATH, then macOS CubeIDE.
ifeq ($(strip $(GCC_PATH)),)
ifeq ($(shell command -v $(PREFIX)gcc 2>/dev/null),)
GCC_PATH := $(shell find /Applications/STM32CubeIDE.app/Contents/Eclipse/plugins -path '*/bin/arm-none-eabi-gcc' -print -quit 2>/dev/null | sed 's,/arm-none-eabi-gcc$$,,')
endif
endif
ifneq ($(strip $(GCC_PATH)),)
CC := "$(GCC_PATH)/$(PREFIX)gcc"
OBJCOPY := "$(GCC_PATH)/$(PREFIX)objcopy"
SIZE := "$(GCC_PATH)/$(PREFIX)size"
else
CC := $(PREFIX)gcc
OBJCOPY := $(PREFIX)objcopy
SIZE := $(PREFIX)size
endif

MCU := -mcpu=cortex-m4 -mthumb -mfpu=fpv4-sp-d16 -mfloat-abi=hard
INCLUDES := -ICore/Inc -IDrivers/STM32G4xx_HAL_Driver/Inc -IDrivers/STM32G4xx_HAL_Driver/Inc/Legacy -IDrivers/CMSIS/Include -IDrivers/CMSIS/Device/ST/STM32G4xx/Include
CPPFLAGS := -DUSE_HAL_DRIVER -DSTM32G474xx $(INCLUDES)
CFLAGS := $(MCU) -std=c11 -Og -g3 -Wall -Wextra -ffunction-sections -fdata-sections -MMD -MP
LDFLAGS := $(MCU) -TSTM32G474RETX_FLASH.ld --specs=nano.specs --specs=nosys.specs -Wl,--gc-sections -Wl,-Map=$(BUILD_DIR)/$(TARGET).map -Wl,--print-memory-usage
C_SOURCES := $(wildcard Core/Src/*.c) $(wildcard Drivers/STM32G4xx_HAL_Driver/Src/*.c)
OBJECTS := $(addprefix $(BUILD_DIR)/,$(C_SOURCES:.c=.o)) $(BUILD_DIR)/startup_stm32g474xx.o
DEPS := $(OBJECTS:.o=.d)

.PHONY: all clean
all: $(BUILD_DIR)/$(TARGET).elf $(BUILD_DIR)/$(TARGET).bin $(BUILD_DIR)/$(TARGET).hex

$(BUILD_DIR)/%.o: %.c Makefile
	@mkdir -p "$(@D)"
	$(CC) $(CPPFLAGS) $(CFLAGS) -c "$<" -o "$@"

$(BUILD_DIR)/startup_stm32g474xx.o: startup_stm32g474xx.s Makefile
	@mkdir -p "$(@D)"
	$(CC) $(MCU) -g3 -x assembler-with-cpp -c "$<" -o "$@"

$(BUILD_DIR)/$(TARGET).elf: $(OBJECTS) STM32G474RETX_FLASH.ld Makefile
	$(CC) $(OBJECTS) $(LDFLAGS) -lc -lm -o "$@"
	$(SIZE) "$@"

$(BUILD_DIR)/%.bin: $(BUILD_DIR)/%.elf
	$(OBJCOPY) -O binary "$<" "$@"

$(BUILD_DIR)/%.hex: $(BUILD_DIR)/%.elf
	$(OBJCOPY) -O ihex "$<" "$@"

clean:
	rm -rf "$(BUILD_DIR)"

-include $(DEPS)
