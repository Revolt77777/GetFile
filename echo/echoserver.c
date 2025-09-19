#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <netdb.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <getopt.h>
#include <sys/socket.h>
#include <netinet/in.h>

#define BUFSIZE 1024

#define USAGE                                                        \
    "usage:\n"                                                         \
    "  echoserver [options]\n"                                         \
    "options:\n"                                                       \
    "  -m                  Maximum pending connections (default: 5)\n" \
    "  -p                  Port (Default: 39483)\n"                    \
    "  -h                  Show this help message\n"

/* OPTIONS DESCRIPTOR ====================================================== */
static struct option gLongOptions[] = {
    {"help",          no_argument,            NULL,           'h'},
    {"maxnpending",   required_argument,      NULL,           'm'},
    {"port",          required_argument,      NULL,           'p'},
    {NULL,            0,                      NULL,             0}
};


int main(int argc, char **argv) {
    int portno = 39483; /* port to listen on */
    int option_char;
    int maxnpending = 5;
  
    // Parse and set command line arguments
    while ((option_char = getopt_long(argc, argv, "p:m:hx", gLongOptions, NULL)) != -1) {
        switch (option_char) {
        case 'h': // help
            fprintf(stdout, "%s ", USAGE);
            exit(0);
            break;
        case 'p': // listen-port
            portno = atoi(optarg);
            break;                                        
        case 'm': // server
            maxnpending = atoi(optarg);
            break; 
        default:
            fprintf(stderr, "%s ", USAGE);
            exit(1);
        }
    }

    setbuf(stdout, NULL); // disable buffering

    if ((portno < 1025) || (portno > 65535)) {
        fprintf(stderr, "%s @ %d: invalid port number (%d)\n", __FILE__, __LINE__, portno);
        exit(1);
    }
    if (maxnpending < 1) {
        fprintf(stderr, "%s @ %d: invalid pending count (%d)\n", __FILE__, __LINE__, maxnpending);
        exit(1);
    }


  /* Socket Code Here */
    //1. Find a proper address for socket
    struct addrinfo hints;
    struct addrinfo *res = NULL;
    char poststr[6];

    memset(&hints, 0, sizeof(hints));
    sprintf(poststr, "%d",  portno);

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
    int ln = listen(listen_fd, maxnpending);
    if (ln == -1) {
        fprintf(stderr, "%s @ %d: listen failed\n", __FILE__, __LINE__);
        close(listen_fd);
        exit(1);
    }

    // 5. Start to accept incoming message
    char buffer[16];
    while (1) {
        int conn_fd = accept(listen_fd, NULL, NULL);
        if (conn_fd == -1) {
            //fprintf(stderr, "%s @ %d: accept failed\n", __FILE__, __LINE__);
            continue;
        }

        // 6. Receive and return the message
        while (1) {
            ssize_t received = recv(conn_fd, buffer, 16,0);
            if (received == -1) {
                //fprintf(stderr, "%s @ %d: recv failed\n", __FILE__, __LINE__);
                close(conn_fd);
                break;
            }
            if (received == 0) {
                //fprintf(stderr, "%s @ %d: closed connection\n", __FILE__, __LINE__);
                close(conn_fd);
                break;
            }

            ssize_t sent = send(conn_fd, buffer, received, 0);
            if (sent == -1) {
                //fprintf(stderr, "%s @ %d: send failed\n", __FILE__, __LINE__);
                close(conn_fd);
                break;
            }
        }
    }
}
