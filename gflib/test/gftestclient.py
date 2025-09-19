""" Getfile Test Client for Abnormal Cases """
import socket
import time
import sys

# Hello, OMSCS 6200 GIOS Spring 2022!
# By: Miguel Paraz <mparaz@gatech.edu>

def send_to_server(buf):
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.connect(("::1", 39485))
    s.send(buf)
    # Just do one read, and not any header and payload logic...
    print(s.recv(8192))
    s.close()


if __name__ == "__main__":
    option = int(sys.argv[1]) if len(sys.argv)>1 else 2
    print(f"option={option}")

    if option == 1:
        # Option 1. Send an complete request.
        send_to_server(b"GETFILE GET /hello\r\n\r\n")
    elif option == 2:
        # Option 2. Send an incomplete request.
        send_to_server(b"GETFILE GET /hellonotrailer")
    elif option == 3:
        # Option 3. Send corrupt headers.
        send_to_server(b"GETFILE  GET /hello")
        send_to_server(b"GETFILE\nGET /hello")
        send_to_server(b"GETFILE\rGET /hello")
        send_to_server(b"GETFILE GET /hello\n\r")
        send_to_server(b"GETFILE GET /hello\r\nX\r\n")
    elif option == 4:
        # Option 4. Send invalid scheme and method
        send_to_server(b"GETFIL GET /hello\r\n\r\n")
        send_to_server(b"GETFILE GE /hello\r\n\r\n")
        send_to_server(b"GETFILEZ GET /hello\r\n\r\n")
        send_to_server(b"GETFILE GETZ /hello\r\n\r\n")
    elif option == 5:
        # Option 5. Support Unix PATH_MAX = 4096, / is included in the count
        filename = "a" * 4095
        send_to_server(bytes("GETFILE GET /" + filename + "\r\n\r\n", "UTF-8"))
    elif option == 6:
        # Option 6. Fail Unix PATH_MAX > 4096, / is included in the count
        filename = "a" * 4096
        send_to_server(bytes("GETFILE GET /" + filename + "\r\n\r\n", "UTF-8"))
    elif option == 7:
        # Option 7, request is sent in tiny pieces
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 10823))
        m = 'GETFILE GET /onebyone\r\n\r\n'
        for b in m:
            print(b)
            s.send(bytes(b, "UTF-8"))
            time.sleep(1)
        # Just do one read, and not any header and payload logic...
        print(s.recv(8192))
        s.close()
    elif option == 8:
        # Option 8. Path is / alone.
        send_to_server(bytes("GETFILE GET /\r\n\r\n", "UTF-8"))
    elif option == 9:
        # Option 9. Path is has no /.
        send_to_server(bytes("GETFILE GET bad\r\n\r\n", "UTF-8"))
    elif option == 10:
        # Option 10. Send an complete request, and read in small pieces with delays.
        # Break this client to cause ECONNRESET on the server recv().
        # This one should break in the payload handling.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 10823))
        s.send(b"GETFILE GET /hello\r\n\r\n")
    
        # No header parsing in this simple client.
        # Python socket.recv() returns empty upon end-of-file.
        while s.recv(256):
            # Don't print the received bytes since this can be anything sent by the server.
            print("SLEEP")
            time.sleep(8640)
            pass
    elif option == 11:
        # Option 11. Send a complete request, but close before receiving the response.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 10823))
        s.send(b"GETFILE GET /hello\r\n\r\n")
        s.close()
    elif option == 12:
        # Option 12. Send an incomplete request, then close.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", 10823))
        s.send(b"GETFILE GET ")
        s.close()

