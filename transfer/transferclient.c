#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <netdb.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <getopt.h>
#include <sys/socket.h>

#define BUFSIZE 512

#define USAGE                                                \
  "usage:\n"                                                 \
  "  transferclient [options]\n"                             \
  "options:\n"                                               \
  "  -s                  Server (Default: localhost)\n"      \
  "  -p                  Port (Default: 29345)\n"            \
  "  -o                  Output file (Default cs6200.txt)\n" \
  "  -h                  Show this help message\n"           \

/* OPTIONS DESCRIPTOR ====================================================== */
static struct option gLongOptions[] = {
    {"output", required_argument, NULL, 'o'},
    {"server", required_argument, NULL, 's'},
    {"help", no_argument, NULL, 'h'},
    {"port", required_argument, NULL, 'p'},
    {NULL, 0, NULL, 0}};

/* Main ========================================================= */
int main(int argc, char **argv)
{
    int option_char = 0;
    unsigned short portno = 29345;
    char *hostname = "localhost";
    char *filename = "cs6200.txt";

    setbuf(stdout, NULL);

    // Parse and set command line arguments
    while ((option_char = getopt_long(argc, argv, "s:p:o:hx", gLongOptions, NULL)) != -1) {
        switch (option_char) {
        case 'p': // listen-port
            portno = atoi(optarg);
            break;
        case 's': // server
            hostname = optarg;
            break;
        default:
            fprintf(stderr, "%s", USAGE);
            exit(1);
        case 'o': // filename
            filename = optarg;
            break;
        case 'h': // help
            fprintf(stdout, "%s", USAGE);
            exit(0);
            break;
        }
    }

    if (NULL == hostname) {
        fprintf(stderr, "%s @ %d: invalid host name\n", __FILE__, __LINE__);
        exit(1);
    }

    if (NULL == filename) {
        fprintf(stderr, "%s @ %d: invalid filename\n", __FILE__, __LINE__);
        exit(1);
    }

    if ((portno < 1025) || (portno > 65535)) {
        fprintf(stderr, "%s @ %d: invalid port number (%d)\n", __FILE__, __LINE__, portno);
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

    // 3. Instantiate the output file descriptor
    int fd = open(filename, O_WRONLY|O_CREAT|O_TRUNC, S_IRUSR|S_IWUSR);
    if (fd == -1) {
        fprintf(stderr, "%s @ %d: failed to open\n", __FILE__, __LINE__);
        close(sfd);
        freeaddrinfo(res);
        exit(1);
    }

    // 4. Try connecting with the server socket
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

    // 5. Start to receive message and write to output file
    char buffer[BUFSIZE];
    ssize_t received = 0;
    while ((received = recv(sfd, buffer, BUFSIZE, 0)) != 0) {
        if (received == -1) {
            fprintf(stderr, "recv() failed\n");
            close(sfd);
            close(fd);
            exit(1);
        }

        ssize_t written = 0;
        while (written < received) {
            ssize_t currWritten = write(fd, buffer, received);
            if (currWritten == -1) {
                fprintf(stderr, "write() failed\n");
                close(sfd);
                close(fd);
                exit(1);
            };
            written += currWritten;
        }
    }
    close(sfd);
    close(fd);
}
