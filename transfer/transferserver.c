#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <netdb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>

#define BUFSIZE 512

#define USAGE                                                \
    "usage:\n"                                               \
    "  transferserver [options]\n"                           \
    "options:\n"                                             \
    "  -f                  Filename (Default: 6200.txt)\n"   \
    "  -p                  Port (Default: 29345)\n"          \
    "  -h                  Show this help message\n"
/* OPTIONS DESCRIPTOR ====================================================== */
static struct option gLongOptions[] = {
    {"filename", required_argument, NULL, 'f'},
    {"help", no_argument, NULL, 'h'},
    {"port", required_argument, NULL, 'p'},
    {NULL, 0, NULL, 0}
};

int main(int argc, char **argv) {
    int portno = 29345; /* port to listen on */
    int option_char;
    char *filename = "6200.txt"; /* file to transfer */

    setbuf(stdout, NULL); // disable buffering

    // Parse and set command line arguments
    while ((option_char = getopt_long(argc, argv, "p:hf:x", gLongOptions, NULL)) != -1) {
        switch (option_char) {
            case 'p': // listen-port
                portno = atoi(optarg);
                break;
            case 'f': // file to transfer
                filename = optarg;
                break;
            case 'h': // help
                fprintf(stdout, "%s", USAGE);
                exit(0);
                break;
            default:
                fprintf(stderr, "%s", USAGE);
                exit(1);
        }
    }


    if ((portno < 1025) || (portno > 65535)) {
        fprintf(stderr, "%s @ %d: invalid port number (%d)\n", __FILE__, __LINE__, portno);
        exit(1);
    }

    if (NULL == filename) {
        fprintf(stderr, "%s @ %d: invalid filename\n", __FILE__, __LINE__);
        exit(1);
    }

    /* Socket Code Here */
    //1. Find a proper address for socket
    struct addrinfo hints;
    struct addrinfo *res = NULL;
    char poststr[6];

    memset(&hints, 0, sizeof(hints));
    sprintf(poststr, "%d", portno);

    hints.ai_family = AF_INET6;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_flags = AI_PASSIVE;

    int rv = getaddrinfo(NULL, poststr, &hints, &res);
    if (rv != 0) {
        fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(rv));
        exit(1);
    }

    // 2. Instantiate the socket
    int listen_fd = socket(res->ai_family, res->ai_socktype, 0);
    if (listen_fd == -1) {
        fprintf(stderr, "%s @ %d: socket creation failed\n", __FILE__, __LINE__);
        freeaddrinfo(res);
        exit(1);
    }

    int yes = 1;
    int so = setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    if (so == -1) {
        fprintf(stderr, "%s @ %d: setsockopt(so)\n", __FILE__, __LINE__);
        close(listen_fd);
        freeaddrinfo(res);
        exit(1);
    }

    // 3. Bind the socket to the address
    int bd = bind(listen_fd, res->ai_addr, res->ai_addrlen);

    freeaddrinfo(res);

    if (bd == -1) {
        fprintf(stderr, "%s @ %d: bind failed\n", __FILE__, __LINE__);
        close(listen_fd);
        exit(1);
    }

    // 4. Turn the socket into passive listen mode
    int ln = listen(listen_fd, 5);
    if (ln == -1) {
        fprintf(stderr, "%s @ %d: listen failed\n", __FILE__, __LINE__);
        close(listen_fd);
        exit(1);
    }

    // 5. Instantiate the file descriptor to read file content
    int fd = open(filename, O_RDONLY);
    if (fd == -1) {
        fprintf(stderr, "%s @ %d: open failed\n", __FILE__, __LINE__);
        close(listen_fd);
        exit(1);
    }

    // 6. Start to accept incoming connections
    char buffer[BUFSIZE];
    while (1) {
        int conn_fd = accept(listen_fd, NULL, NULL);
        if (conn_fd == -1) {
            //fprintf(stderr, "%s @ %d: accept failed\n", __FILE__, __LINE__);
            continue;
        }

        // 7. Start to read and sent until all bytes are sent
        __off_t reset = lseek(fd, 0, SEEK_SET);
        if (reset == -1) {
            fprintf(stderr, "%s @ %d: seek failed\n", __FILE__, __LINE__);
            close(conn_fd);
            close(listen_fd);
            exit(1);
        }

        ssize_t rd = read(fd, buffer, BUFSIZE);
        while (rd != 0) {
            if (rd == -1) {
                fprintf(stderr, "%s @ %d: read failed\n", __FILE__, __LINE__);
                close(fd);
                close(listen_fd);
                close(conn_fd);
                exit(1);
            }

            ssize_t sent = 0;
            while (sent < rd) {
                ssize_t currSent = send(conn_fd, buffer, rd, 0);
                if (currSent == -1) {
                    fprintf(stderr, "%s @ %d: send failed\n", __FILE__, __LINE__);
                    close(fd);
                    close(listen_fd);
                    close(conn_fd);
                    exit(1);
                }
                sent += currSent;
            }

            rd = read(fd, buffer, BUFSIZE);
        }
        close(conn_fd);
    }
}
