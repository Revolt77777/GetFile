#include <stdlib.h>
#include <stdio.h>
#include <ctype.h>
#include <string.h>

// hexdump helper code
// by Miguel Paraz <mparaz@gatech.edu>

void hexdump_line(const unsigned char *buffer, size_t size, int line_length)
{
  const char *hexdump_prefix = "DUMP: ";
  int hexdump_prefix_len = strlen(hexdump_prefix);

  size_t nchars = hexdump_prefix_len + (line_length * 3) + line_length + 1;
  char printbuf[nchars + 1];

  memcpy(printbuf, hexdump_prefix, hexdump_prefix_len);
  memset(printbuf + hexdump_prefix_len, ' ', nchars - hexdump_prefix_len);

  char *p1 = printbuf + hexdump_prefix_len;
  char *p2 = printbuf + hexdump_prefix_len + (line_length * 3);

  while (size--)
  {
    unsigned char ch = *buffer++;

    char hexbuf[4];
    snprintf(hexbuf, 4, "%02x ", ch);
    *p1++ = hexbuf[0];
    *p1++ = hexbuf[1];
    *p1++ = hexbuf[2];

    if (isprint(ch))
    {
      *p2++ = ch;
    }
    else
    {
      *p2++ = '.';
    }
  }

  *p2++ = '\n';
  *p2++ = 0;
  fputs(printbuf, stderr);
}

void hexdump(const unsigned char *buffer, size_t size)
{
  size_t line_length = 16;
  int lines = size / line_length;
  while (lines--) {
    hexdump_line(buffer, line_length, line_length);
    buffer += line_length;
  }
  hexdump_line(buffer, size % line_length, line_length);
}

int main(int argc, const char **argv)
{
    char debugme[] = "Debugging OMSCS GIOS 6200 is\r\nFUN!!!";

    hexdump(debugme, sizeof(debugme));
    return EXIT_SUCCESS;
}

