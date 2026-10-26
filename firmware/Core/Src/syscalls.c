/* Minimal newlib support. The command shell itself uses explicit HAL I/O. */
#include "main.h"
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/stat.h>

void *_sbrk(ptrdiff_t increment)
{
    extern uint8_t _end;
    extern uint8_t _Min_Heap_Size;
    static uintptr_t heap_end;
    const uintptr_t start = (uintptr_t)&_end;
    const uintptr_t limit = start + (uintptr_t)&_Min_Heap_Size;
    if (!heap_end) heap_end = start;
    if ((increment >= 0 && (uintptr_t)increment > limit - heap_end) ||
        (increment < 0 && (uintptr_t)(-(increment + 1)) + 1U > heap_end - start)) {
        errno = ENOMEM;
        return (void *)-1;
    }
    uintptr_t previous = heap_end;
    heap_end += increment;
    return (void *)previous;
}
int _write(int file, char *buffer, int length)
{
    if ((file != 1 && file != 2) || length < 0) { errno = EBADF; return -1; }
    if (HAL_UART_Transmit(&hlpuart1, (const uint8_t *)buffer,
                          (uint16_t)length, 1000U) != HAL_OK) {
        errno = EIO; return -1;
    }
    return length;
}
int _read(int file, char *buffer, int length)
{
    (void)file; (void)buffer; (void)length;
    errno = EAGAIN; return -1;
}
int _close(int file) { (void)file; errno = EBADF; return -1; }
int _lseek(int file, int offset, int origin)
{
    (void)file; (void)offset; (void)origin;
    errno = ESPIPE; return -1;
}
int _fstat(int file, struct stat *status)
{
    (void)file; status->st_mode = S_IFCHR; return 0;
}
int _isatty(int file) { return file >= 0 && file <= 2; }
int _getpid(void) { return 1; }
int _kill(int pid, int signal)
{
    (void)pid; (void)signal; errno = EINVAL; return -1;
}
void _exit(int status) { (void)status; Error_Handler(); for (;;) {} }
