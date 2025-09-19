#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <sys/types.h>
#include <string.h>
#include <errno.h>
#include <sys/socket.h>
#include <netdb.h>
#include <netinet/in.h>
#include <getopt.h>

/* Be prepared accept a response of this length */
#define BUFSIZE 1024

#define USAGE                                                                       \
    "usage:\n"                                                                      \
    "  echoclient [options]\n"                                                      \
    "options:\n"                                                                    \
    "  -s                  Server (Default: localhost)\n"                           \
    "  -m                  Message to send to server (Default: \"Hello Spring!!\")\n" \
    "  -p                  Port (Default: 39483)\n"                                  \
    "  -h                  Show this help message\n"

/* OPTIONS DESCRIPTOR ====================================================== */
static struct option gLongOptions[] = {
    {"port", required_argument, NULL, 'p'},
    {"server", required_argument, NULL, 's'},
    {"help", no_argument, NULL, 'h'},
    {"message", required_argument, NULL, 'm'},
    {NULL, 0, NULL, 0}};

/* Main ========================================================= */
int main(int argc, char **argv)
{
    int option_char = 0;
    unsigned short portno = 39483;
    char *hostname = "localhost";
    char *message = "Hello Fall!!";

    // Parse and set command line arguments
    while ((option_char = getopt_long(argc, argv, "s:p:m:hx", gLongOptions, NULL)) != -1) {
        switch (option_char) {
        case 'p': // listen-port
            portno = atoi(optarg);
            break;
        case 'm': // message
            message = optarg;
            break;
        case 's': // server
            hostname = optarg;
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

    setbuf(stdout, NULL); // disable buffering

    if ((portno < 1025) || (portno > 65535)) {
        fprintf(stderr, "%s @ %d: invalid port number (%d)\n", __FILE__, __LINE__, portno);
        exit(1);
    }

    if (NULL == message) {
        fprintf(stderr, "%s @ %d: invalid message\n", __FILE__, __LINE__);
        exit(1);
    }

    if (NULL == hostname) {
        fprintf(stderr, "%s @ %d: invalid host name\n", __FILE__, __LINE__);
        exit(1);
    }

    /* Socket Code Here */
    //1. Resolve the server's address for socket
    struct addrinfo hints;
    struct addrinfo *res = NULL;
    char poststr[6];

    memset(&hints, 0, sizeof(hints));
    sprintf(poststr, "%d",  portno);

    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    int rv = getaddrinfo(hostname, poststr, &hints, &res);
    if (rv != 0) {
        fprintf(stderr, "getaddrinfo: %s\n", gai_strerror(rv));
        exit(1);
    }

    // 2. Instantiate the socket
    int sfd = socket(res->ai_family, res->ai_socktype, 0);
    if (sfd == -1) {
        fprintf(stderr, "%s @ %d: socket creation failed\n", __FILE__, __LINE__);
        freeaddrinfo(res);
        exit(1);
    }

    // 3. Try connecting with the server socket
    int connected = 0;
    while (res != NULL) {
        int cn = connect(sfd, res->ai_addr, res->ai_addrlen);
        if (cn == 0) {
            connected = 1;
            break;
        }
        res = res->ai_next;
    }

    freeaddrinfo(res);

    if (!connected) {
        fprintf(stderr, "Failed to connect\n");
        close(sfd);
        exit(1);
    }

    // 4. Start to send message and print returned message
    size_t length = strlen(message);

    ssize_t s = send(sfd, message, length, 0);
    if (s == -1) {
        fprintf(stderr, "send failed\n");
        close(sfd);
        exit(1);
    }

    char received[16];
    ssize_t r = recv(sfd, received, 16, 0);
    if (r == -1) {
        fprintf(stderr, "recv failed\n");
        close(sfd);
        exit(1);
    }
    if (r == 0) {
        fprintf(stderr, "Connection closed\n");
        close(sfd);
        exit(0);
    }
    fwrite(received, 1, r, stdout);
}
