/*
 *  This file is for use by students to define anything they wish.  It is used by both the gf server and client implementations
 */
#ifndef __GF_STUDENT_H__
#define __GF_STUDENT_H__

#include <errno.h>
#include <string.h>
#include <netdb.h>
#include <unistd.h>
#include <regex.h>
#include <resolv.h>
#include <getopt.h>
#include <sys/stat.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/signal.h>
#include <sys/socket.h>
#include <netinet/in.h>


// Finding the correct address for socket
struct addrinfo *findAddrInfo(int ai_family, unsigned short portno, char *server);


 #endif // __GF_STUDENT_H__
