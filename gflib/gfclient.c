#include <stdlib.h>

#include "gfclient-student.h"

// Modify this file to implement the interface specified in
// gfclient.h.

struct gfcrequest_t {
    char *server;
    unsigned short portno;
    char *path;
    int sfd;
    void (*writefunc)(void *data, size_t data_len, void *arg);
    void *writearg;
    gfstatus_t status;
    size_t fileLength;
    size_t bytesReceived;
};

static void gfc_close_socket(gfcrequest_t *req) {
    if (req && req->sfd >= 0) {
        close(req->sfd);
        req->sfd = -1;
    }
}

// optional function for cleanup processing.
void gfc_cleanup(gfcrequest_t **gfr) {
    if (gfr == NULL || *gfr == NULL) return;
    gfcrequest_t *req = *gfr;
    gfc_close_socket(req);
    if (req->server) {
        free(req->server);
        req->server = NULL;
    }
    if (req->path) {
        free(req->path);
        req->path = NULL;
    }
    free(req);
    *gfr = NULL;
}

size_t gfc_get_filelen(gfcrequest_t **gfr) {
    return (*gfr)->fileLength;
}

size_t gfc_get_bytesreceived(gfcrequest_t **gfr) {
    return (*gfr)->bytesReceived;
}

gfcrequest_t *gfc_create() {
    gfcrequest_t *gfr = malloc(sizeof(gfcrequest_t));

    // Initialize fields to safe defaults
    gfr->server = NULL;
    gfr->path = NULL;
    gfr->sfd = -1;
    gfr->writefunc = NULL;
    gfr->writearg = NULL;
    gfr->status = GF_INVALID;
    gfr->fileLength = 0;
    gfr->bytesReceived = 0;

    return gfr;
}


gfstatus_t gfc_get_status(gfcrequest_t **gfr) {
    return (*gfr)->status;
}

void gfc_global_init() {
}

void gfc_global_cleanup() {
}

int establishConnection(gfcrequest_t **gfr) {
    struct addrinfo *addr = findAddrInfo(AF_UNSPEC, (*gfr)->portno, (*gfr)->server);
    struct addrinfo *rp;
    int sfd = -1;
    int connected = 0;

    for (rp = addr; rp != NULL; rp = rp->ai_next) {
        sfd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (sfd == -1) {
            continue;
        }
        if (connect(sfd, rp->ai_addr, rp->ai_addrlen) == 0) {
            connected = 1;
            break;
        }
        close(sfd);
        sfd = -1;
    }

    if (addr)
        freeaddrinfo(addr);

    if (!connected) {
        fprintf(stderr, "Connection Failed!\n");
        (*gfr)->status = GF_INVALID;
        (*gfr)->sfd = -1;
        return -1;
    }
    (*gfr)->sfd = sfd;
    return 0;
}

int gfc_perform(gfcrequest_t **gfr) {
    // Create the request message first
    char buffer[1024];
    sprintf(buffer, "GETFILE GET %s\r\n\r\n", (*gfr)->path);

    if (establishConnection(gfr) == -1) {
        gfc_close_socket(*gfr);
        return -1;
    };

    // Send out the header to server/client
    ssize_t sent = 0;
    ssize_t headerLength = strlen(buffer);

    while (sent < headerLength) {
        ssize_t currSent = send((*gfr)->sfd, buffer + sent, headerLength - sent, 0);
        if (currSent == -1) {
            fprintf(stderr, "%s @ %d: send failed\n", __FILE__, __LINE__);
            gfc_close_socket(*gfr);
            return -1;
        }
        sent += currSent;
    }

    // fprintf(stdout, "Sent Header: %lu\n", headerLength);
    memset(buffer, 0, sizeof(buffer));

    // Receive header response from server
    ssize_t prevLength = 0;
    ssize_t received = 0;
    ssize_t header_end = 0;
    int header_found = 0;
    while (header_found == 0) {
        received = recv((*gfr)->sfd, buffer + prevLength, sizeof(buffer) - prevLength, 0);

        if (received == 0) {
            break;
        }
        if (received == -1) {
            fprintf(stderr, "%s @ %d: receive failed\n", __FILE__, __LINE__);
            gfc_close_socket(*gfr);
            return -1;
        }
        // scan the current buffer to delimiter
        ssize_t currentLength = prevLength + received;
        ssize_t start = (prevLength >= 3) ? (prevLength - 3) : 0;
        for (ssize_t i = start; i + 3 < currentLength; i++) {
            if (buffer[i] == '\r' &&
                buffer[i + 1] == '\n' &&
                buffer[i + 2] == '\r' &&
                buffer[i + 3] == '\n') {
                // Found it!
                header_end = i; // index of the '\r' that starts the sequence
                header_found = 1;
                break;
            }
        }
        prevLength = currentLength;
    }
    // fprintf(stdout, "Received Header: %.*s\n", (int) header_end, buffer);
    // fprintf(stdout, "Leftover: %s\n", buffer + header_end + 4);

    // Deal with the header from 0 to header_end - 1
    // 0 to 6: GETFILE
    ssize_t start = 0;
    if (memcmp(buffer, "GETFILE", 7) != 0) {
        (*gfr)->status = GF_INVALID;
        gfc_close_socket(*gfr);
        return -1;
    }
    // 8 to x: status
    start = 8;
    ssize_t end = 8;
    while (end < header_end && buffer[end] != ' ') {
        end++;
    }
    ssize_t tokenLength = end - start;
    if (tokenLength == 2 && memcmp(buffer + start, "OK", 2) == 0) {
        (*gfr)->status = GF_OK;
    } else if (tokenLength == 14 && memcmp(buffer + start, "FILE_NOT_FOUND", 14) == 0) {
        (*gfr)->status = GF_FILE_NOT_FOUND;
        gfc_close_socket(*gfr);
        return 0;
    } else if (tokenLength == 5 && memcmp(buffer + start, "ERROR", 5) == 0) {
        (*gfr)->status = GF_ERROR;
        gfc_close_socket(*gfr);
        return 0;
    } else {
        (*gfr)->status = GF_INVALID;
        gfc_close_socket(*gfr);
        return -1;
    }
    // x+1 to header_end - 1: length
    start = end + 1;
    for (size_t i = start; i < header_end; i++) {
        char c = buffer[i];
        if (c < '0' || c > '9') {
            (*gfr)->status = GF_INVALID;
            gfc_close_socket(*gfr);
            return -1;
        }
        (*gfr)->fileLength = (*gfr)->fileLength * 10 + (c - '0');
    }
    // fprintf(stdout, "Length: %lu\n", (*gfr)->fileLength);

    // Deal with the rest content in the buffer
    ssize_t leftover = prevLength - (header_end + 4); // 4 = "\r\n\r\n"
    (*gfr)->bytesReceived = (leftover > 0) ? leftover : 0;

    if ((*gfr)->bytesReceived > 0 && (*gfr)->writefunc) {
        (*gfr)->writefunc(buffer + header_end + 4, (*gfr)->bytesReceived, (*gfr)->writearg);
        // fprintf(stdout, "Wrote Progress: %lu/%lu\n", (*gfr)->bytesReceived, (*gfr)->fileLength);
    }

    // Repeated receive chunks and write
    while ((*gfr)->bytesReceived < (*gfr)->fileLength) {
        ssize_t currRecv = recv((*gfr)->sfd, buffer, 1024, 0);
        if (currRecv == -1) {
            fprintf(stderr, "%s @ %d: recv failed\n", __FILE__, __LINE__);
            (*gfr)->status = GF_INVALID;
            gfc_close_socket(*gfr);
            return -1;
        }
        if (currRecv == 0) {
            // connection closed early
            fprintf(stderr, "Connection closed early, bytes received: %lu, fileLength: %lu\n", (*gfr)->bytesReceived,
                    (*gfr)->fileLength);
            gfc_close_socket(*gfr);
            return -1;
        }

        (*gfr)->bytesReceived += currRecv;
        if ((*gfr)->writefunc) {
            (*gfr)->writefunc(buffer, currRecv, (*gfr)->writearg);
            // fprintf(stdout, "Wrote Progress: %lu/%lu\n", (*gfr)->bytesReceived, (*gfr)->fileLength);
        }
    }

    // fprintf(stdout, "File Transfer Finished!\n");
    gfc_close_socket(*gfr);
    return 0;
}

void gfc_set_port(gfcrequest_t **gfr, unsigned short port) {
    (*gfr)->portno = port;
}

void gfc_set_server(gfcrequest_t **gfr, const char *server) {
    if ((*gfr)->server) {
        free((*gfr)->server);
    }
    (*gfr)->server = strdup(server);
}

void gfc_set_headerfunc(gfcrequest_t **gfr, void (*headerfunc)(void *, size_t, void *)) {
}

void gfc_set_headerarg(gfcrequest_t **gfr, void *headerarg) {
}

void gfc_set_path(gfcrequest_t **gfr, const char *path) {
    if ((*gfr)->path) {
        free((*gfr)->path);
    }
    (*gfr)->path = strdup(path);
}

void gfc_set_writefunc(gfcrequest_t **gfr, void (*writefunc)(void *, size_t, void *)) {
    (*gfr)->writefunc = writefunc;
}

void gfc_set_writearg(gfcrequest_t **gfr, void *writearg) {
    (*gfr)->writearg = writearg;
}

const char *gfc_strstatus(gfstatus_t status) {
    const char *strstatus = "UNKNOWN";

    switch (status) {
        case GF_OK: {
            strstatus = "OK";
        }
        break;

        case GF_FILE_NOT_FOUND: {
            strstatus = "FILE_NOT_FOUND";
        }
        break;

        case GF_INVALID: {
            strstatus = "INVALID";
        }
        break;

        case GF_ERROR: {
            strstatus = "ERROR";
        }
        break;
    }

    return strstatus;
}
