/* ee_printf for the sim-control platform.
 *
 * CoreMark ships barebones/ee_printf.c as a template whose output hook,
 * uart_send_char(), is an `#error` stub. Rather than fill that stub in
 * -- which would mean shipping a modified copy of a CoreMark source --
 * this is a small independent implementation covering exactly the
 * conversions the unmodified benchmark sources use.
 *
 * With HAS_FLOAT 0 those are: %d, %u, %lu, %x (with zero-padded width,
 * as %04x), %s and %%. Anything else is emitted literally so a format
 * this does not handle shows up in the output instead of being silently
 * dropped.
 *
 * Output goes one character at a time to the sim-control character
 * register. There is no buffering: the harness is reading the writes as
 * they happen, and a run that dies mid-line should still show the line
 * up to that point.
 *
 * SPDX-License-Identifier: Apache-2.0
 */
#include <stdarg.h>

#include "coremark.h"
#include "sim_ctrl.h"

static int emit(char c)
{
    sim_putchar(c);
    return 1;
}

/* Digits are generated least-significant first into a scratch buffer and
 * then replayed, which is what keeps this free of division by anything
 * but the base -- relevant on rv32i, where every divide is a libgcc
 * call on the measured path. */
static int emit_num(unsigned long value,
                    unsigned int  base,
                    int           width,
                    int           zero_pad,
                    int           negative)
{
    char digits[] = "0123456789abcdef";
    char buf[24];
    int  len = 0;
    int  n   = 0;

    do
    {
        buf[len++] = digits[value % base];
        value /= base;
    } while (value != 0 && len < (int)sizeof(buf));

    if (negative)
    {
        if (zero_pad)
        {
            /* A minus sign belongs outside the zero padding. */
            n += emit('-');
            width--;
        }
        else
        {
            buf[len++] = '-';
        }
    }

    while (len < width)
    {
        n += emit(zero_pad ? '0' : ' ');
        width--;
    }

    while (len > 0)
    {
        n += emit(buf[--len]);
    }

    return n;
}

int ee_printf(const char *fmt, ...)
{
    va_list args;
    int     n = 0;

    va_start(args, fmt);

    while (*fmt)
    {
        int width    = 0;
        int zero_pad = 0;

        if (*fmt != '%')
        {
            n += emit(*fmt++);
            continue;
        }

        fmt++; /* past '%' */

        if (*fmt == '0')
        {
            zero_pad = 1;
            fmt++;
        }
        while (*fmt >= '0' && *fmt <= '9')
        {
            width = width * 10 + (*fmt++ - '0');
        }
        /* Length modifiers are parsed and ignored: every integer in
         * play is 32 bits on these cores, so %lu and %u are the same
         * argument. */
        while (*fmt == 'l' || *fmt == 'h')
        {
            fmt++;
        }

        switch (*fmt)
        {
            case 'd':
            case 'i':
            {
                int           v = va_arg(args, int);
                unsigned long m = (v < 0) ? (unsigned long)(-(long)v)
                                          : (unsigned long)v;
                n += emit_num(m, 10, width, zero_pad, v < 0);
                fmt++;
                break;
            }
            case 'u':
                n += emit_num(va_arg(args, unsigned int), 10, width, zero_pad, 0);
                fmt++;
                break;
            case 'x':
            case 'X':
                n += emit_num(va_arg(args, unsigned int), 16, width, zero_pad, 0);
                fmt++;
                break;
            case 'c':
                n += emit((char)va_arg(args, int));
                fmt++;
                break;
            case 's':
            {
                const char *s = va_arg(args, const char *);
                if (s == NULL)
                {
                    s = "(null)";
                }
                while (*s)
                {
                    n += emit(*s++);
                }
                fmt++;
                break;
            }
            case '%':
                n += emit('%');
                fmt++;
                break;
            default:
                /* Unhandled conversion: show it rather than swallow it.
                 * No argument is consumed, so the rest of the line will
                 * be wrong -- which is the point, it should be
                 * noticeable. */
                n += emit('%');
                if (*fmt)
                {
                    n += emit(*fmt++);
                }
                break;
        }
    }

    va_end(args);
    return n;
}
