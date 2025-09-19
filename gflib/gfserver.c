#include <stdlib.h>

#include "gfserver-student.h"

// Modify this file to implement the interface specified in
 // gfserver.h.

struct gfserver_t {
    unsigned short port;
    gfh_error_t (*handler)(gfcontext_t **, const char *, void*);
    void* arg;
    int max_npending;
    int listen_fd;
};

struct gfcontext_t {
    int conn_fd;
};

void gfs_cleanup(gfserver_t *gfs) {
    if (gfs->listen_fd != -1) {
        close(gfs->listen_fd);
    }
    free(gfs);
}

void gfs_abort(gfcontext_t **ctx){
    if (ctx && *ctx) {
        close((*ctx)->conn_fd);
        free(*ctx);
        *ctx = NULL;
    }
}

ssize_t gfs_send(gfcontext_t **ctx, const void *data, size_t len){
    if (!ctx || !*ctx) {
        return -1;  // Connection was aborted
    }

    // fprintf(stdout, "Sending %lu data from %p\n", len, data);
    ssize_t sent = 0;
    while (sent < len) {
        ssize_t currSent = send((*ctx)->conn_fd, data+sent, len - sent, 0);
        if (currSent == -1) {
            fprintf(stderr, "%s @ %d: file send failed\n", __FILE__, __LINE__);
            return -1;
        }
        sent += currSent;
    }
    return sent;
}

ssize_t gfs_sendheader(gfcontext_t **ctx, gfstatus_t status, size_t file_len){
    if (!ctx || !*ctx) {
        return -1;  // Connection was aborted
    }

    char buffer[1024];
    ssize_t header_length = 0;
    switch (status) {
        case GF_OK:
            header_length = sprintf(buffer, "GETFILE OK %lu\r\n\r\n", file_len);
            break;
        case GF_ERROR:
            header_length = sprintf(buffer, "GETFILE ERROR\r\n\r\n");
            break;
        case GF_INVALID:
            header_length = sprintf(buffer, "GETFILE INVALID\r\n\r\n");
            break;
        case GF_FILE_NOT_FOUND:
            header_length = sprintf(buffer, "GETFILE FILE_NOT_FOUND\r\n\r\n");
            break;
    }

    // fprintf(stdout, "Sending header: %s", buffer);
    ssize_t sent = 0;
    while (sent < header_length) {
        ssize_t sd = send((*ctx)->conn_fd, buffer+sent, header_length - sent, 0);
        if (sd < 0) {
            fprintf(stderr, "%s @ %d: header send failed\n", __FILE__, __LINE__);
            return -1;
        }
        sent += sd;
    }

    // fprintf(stdout, "Sent header: %s\n", buffer);
    return header_length;
}

gfserver_t* gfserver_create(){
    gfserver_t *gfs = malloc(sizeof(gfserver_t));

    gfs->handler = NULL;
    gfs->arg = NULL;
    gfs->max_npending = 0;
    gfs->listen_fd = -1;

    return gfs;
}

void gfserver_set_port(gfserver_t **gfs, unsigned short port) {
    (*gfs)->port = port;
}

void gfserver_set_handlerarg(gfserver_t **gfs, void* arg) {
    (*gfs)->arg = arg;
}

int gfserver_setup_socket(gfserver_t **gfs) {
    struct addrinfo *addr = findAddrInfo(AF_UNSPEC, (*gfs)->port, NULL);
    if(addr == NULL) {
        fprintf(stderr, "Unable to find an address\n");
        return -1;
    }

    int listen_fd = socket(addr->ai_family, addr->ai_socktype, addr->ai_protocol);
    if(listen_fd == -1) {
        fprintf(stderr, "Unable to create socket\n");
        freeaddrinfo(addr);
        return -1;
    }

    int yes = 1;
    int so = setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    if (so == -1) {
        fprintf(stderr, "%s @ %d: setsockopt(so)\n", __FILE__, __LINE__);
        close(listen_fd);
        freeaddrinfo(addr);
        return -1;
    }

    int bd = bind(listen_fd, addr->ai_addr, addr->ai_addrlen);

    freeaddrinfo(addr);

    if (bd == -1) {
        fprintf(stderr, "%s @ %d: bind failed\n", __FILE__, __LINE__);
        close(listen_fd);
        return -1;
    }

    int ln = listen(listen_fd, 5);
    if (ln == -1) {
        fprintf(stderr, "%s @ %d: listen failed\n", __FILE__, __LINE__);
        close(listen_fd);
        return -1;
    }

    (*gfs)->listen_fd = listen_fd;
    return 0;
}

void gfserver_serve(gfserver_t **gfs) {
    if (gfserver_setup_socket(gfs) == -1) {
        gfs_cleanup(*gfs);
        return;
    }
    // Start infinite loop to accept new connection
    char header[1024];
    while (1) {
        int conn_fd = accept((*gfs)->listen_fd, NULL, NULL);
        if (conn_fd == -1) {
            fprintf(stderr, "%s @ %d: accept failed\n", __FILE__, __LINE__);
            continue;
        }

        // New connection accepted, initialize the context info
        gfcontext_t *ctx = malloc(sizeof(gfcontext_t));
        ctx->conn_fd = conn_fd;
        // fprintf(stdout, "Connected with %d\n", conn_fd);

        // receive the header
        ssize_t header_length = 0;
        int header_found = 0;
        while (!header_found) {
            ssize_t received = recv(ctx->conn_fd, header + header_length, sizeof(header) - header_length - 1, 0);
            if (received == 0) {
                break;
            }
            if (received == -1) {
                fprintf(stderr, "%s @ %d: receive failed\n", __FILE__, __LINE__);
                close(ctx->conn_fd);
                free(ctx);
                break;
            }
            header_length += received;

            // Look for header end delimiter starting from a safe position
            ssize_t start = (header_length >= 4) ? header_length - received - 3 : 0;
            if (start < 0) start = 0;

            for (ssize_t i = start; i <= header_length - 4; i++) {
                if (header[i] == '\r' && header[i+1] == '\n' &&
                    header[i+2] == '\r' && header[i+3] == '\n') {
                    header_found = 1;
                    break;
                }
            }
        }
        // fprintf(stdout, "Received Header: %s\n", header);

        // Header received complete, parse the header
        // Check the length, it should at least have 16 chars
        if (header_length < 16) {
            fprintf(stderr, "%s @ %d: received wrong header\n", __FILE__, __LINE__);
            gfs_sendheader(&ctx, GF_INVALID, 0);
            close(ctx->conn_fd);
            free(ctx);
            continue;
        }
        // 0 to 11: GETFILE GET
        if (memcmp(header, "GETFILE GET ", 12) != 0) {
            fprintf(stderr, "%s @ %d: received wrong header\n", __FILE__, __LINE__);
            gfs_sendheader(&ctx, GF_INVALID, 0);
            close(ctx->conn_fd);
            free(ctx);
            continue;
        }

        // Check that path starts with '/'
        if (header[12] != '/') {
            fprintf(stderr, "%s @ %d: path must start with /\n", __FILE__, __LINE__);
            gfs_sendheader(&ctx, GF_INVALID, 0);
            close(ctx->conn_fd);
            free(ctx);
            continue;
        }

        // header_length-4 to header_length-1: \r\n\r\n
        if (header[header_length-1] != '\n' ||
            header[header_length-2] != '\r' ||
            header[header_length-3] != '\n' ||
            header[header_length-4] != '\r')
        {
            fprintf(stderr, "%s @ %d: received wrong header\n", __FILE__, __LINE__);
            gfs_sendheader(&ctx, GF_INVALID, 0);
            close(ctx->conn_fd);
            free(ctx);
            continue;
        }
        // 12 to header_length-5: path
        header[header_length - 4] = '\0';  // Replace first '\r' with null terminator

        // Pass the path to handler
        (*gfs)->handler(&ctx, header + 12, (*gfs)->arg);
    }
}

void gfserver_set_handler(gfserver_t **gfs, gfh_error_t (*handler)(gfcontext_t **, const char *, void*)) {
    (*gfs)->handler = handler;
}

void gfserver_set_maxpending(gfserver_t **gfs, int max_npending) {
    (*gfs)->max_npending = max_npending;
}