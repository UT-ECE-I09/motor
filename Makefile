PYTHON ?= python3
.PHONY: all clean flash probe console demo test
all:
	$(MAKE) -C firmware
clean:
	$(MAKE) -C firmware clean
flash: all
	$(PYTHON) tools/flash.py
probe:
	$(PYTHON) tools/flash.py --probe
console:
	$(PYTHON) tools/uart_console.py
demo:
	$(PYTHON) tools/uart_console.py --demo --log logs/uart-demo.log
test:
	$(PYTHON) -m unittest discover -s tests -v
