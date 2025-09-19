/*
 *  This file is for use by students to define anything they wish.  It is used by both the gf server and client implementations
 */

#include <stdlib.h>
#include "gf-student.h"

struct addrinfo *findAddrInfo(int ai_family, unsigned short portno, char *server) {
    struct addrinfo hints;
    struct addrinfo *res = NULL;
    char poststr[6];

    memset(&hints, 0, sizeof(hints));
    snprintf(poststr, sizeof(poststr), "%hu", portno);

    hints.ai_family = ai_family;
    hints.ai_socktype = SOCK_STREAM;

    int rv = getaddrinfo(server, poststr, &hints, &res);
    if (rv != 0) {
        fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(rv));
    }
    return res;
}




