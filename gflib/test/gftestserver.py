""" Getfile Test Server for Abnormal Cases """
import socket
import time
import random
import hashlib
import sys
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor

# Hello, OMSCS 6200 GIOS Spring 2022!
# By: Miguel Paraz <mparaz@gatech.edu>

# Use optimised random function if available
# Thanks to Vladimir.

# hacked on by Patrick Jacobs <pjacobs7@gatech.edu> Summer 2025


def slow_random_bytes(buffer_size):
    return bytes([random.randint(0, 255) for _ in range(0, buffer_size)])

random_bytes = None

if importlib.util.find_spec("numpy"):
    print("numpy found")
    import numpy as np
    random_bytes = np.random.bytes
else:
    print("numpy not found, consider: pip install numpy")
    random_bytes = slow_random_bytes


def handle_connection(s, option, file_hashes):
    """Handle a single client connection."""
    try:
        # Receive and show the header, don't do anything with it
        req = s.recv(8192)
        print(req)

        # Parse the request properly
        request_str = str(req, 'utf-8')  # Convert bytes to string
        parts = request_str.split()
        if len(parts) >= 3:
            requested_path = parts[2]  # Gets '/courses/ud923/filecorpus/road.jpg\r\n\r\n'
            clean_path = requested_path.split('\r')[0]  # Remove \r\n\r\n
            filename = clean_path.replace('/', '_').lstrip('_')  # Convert /path/to/file.jpg -> path_to_file.jpg
            path = f'./{filename}_{req_num:04d}'
        else:
            path = f'./unknown_{req_num:04d}'


        print(f"DEBUG: Handling connection, option={option}")
        if option == 1:
            # Option 1.  # Do not send anything.
            # Break this server and the client recv() may ECONNRESET if it is waiting for data.
            pass
        elif option == 2:
            # Option 2. Send the header, in two pieces. Then send 1 byte payload. Client should succeed.
            s.send(b"GETFILE OK ")
            # time.sleep(1)
            s.send(b"1\r\n\r\nX")
            s.close()
        elif option == 3:
            # Option 3. Send the header, in pieces, with enough time to interrupt. Then send 1 byte payload.
            # Break this server to cause ECONNRESET on the client recv() in the header processing.
            s.send(b"GETFILE OK ")
            time.sleep(3600)
            s.send(b"1\r\n\r\nX")
        elif option == 4:
            # Option 4. Send rubbish payload, slowly. Break this server to cause ECONNRESET on the client recv()
            # in the payload processing.
            s.send(b"GETFILE OK 123456789\r\n\r\n")
            while True:
                s.send(b"abcd")
                time.sleep(1)
        elif option == 5:
            # Option 5. Send a non-decimal length
            s.send(b"GETFILE OK badlengthisbad\r\n\r\n")
        elif option == 6:
            # Option 6. Send a bad character in the middle of the CR LF
            s.send(b"GETFILE OK 123\r\n!\r\n")
        elif option == 7:
            # Option 7. Send a file containing CR LF
            s.send(b"GETFILE OK 2\r\n\r\n\r\n")
            s.recv(10)
        elif option == 8:
            # Option 8. Send a file containing CR LF CR LF
            s.send(b"GETFILE OK 4\r\n\r\n\r\n\r\n")
        elif option == 9:
            # Option 9. Send incomplete header and close the connection
            s.send(b"GETFILE OK 5\r\n\r")
            s.close()
        elif option == 10:
            # Option 10. Send FILE_NOT_FOUND status.
            s.send(b"GETFILE FILE_NOT_FOUND\r\n\r\n")
        elif option == 11:
            # Option 11. Send ERROR status.
            print("DEBUG: In option 11 block")
            s.send(b"GETFILE ERROR\r\n\r\n")
            print("DEBUG: Sent response")
            time.sleep(0.2)
            print("DEBUG: About to close")
            s.close()
            print("DEBUG: Closed")

        elif option == 12:
            # Option 12. Send INVALID status.
            s.send(b"GETFILE INVALID\r\n\r\n")
        elif option == 13:
            # Option 13. Send wrong scheme.
            s.send(b"POSTFILE OK 4\r\n\r\nabcd")
        elif option == 14:
            # Option 14. Send status not in set.
            s.send(b"GETFILE WRONG\r\n\r\n")
        elif option == 1000:
            # Serve a 2 GB + extra_bytes (exceeds int) file
            # This can be verified with: sha1sum filename.
            hash = hashlib.sha1()
            extra_bytes = 1
            orig_size = 2**31 + extra_bytes
            size = orig_size
            buffer_size = 8192

            s.send(bytes(f"GETFILE OK {size}\r\n\r\n", "UTF-8"))
            while size > extra_bytes:
                random_buffer = random_bytes(buffer_size)
                hash.update(random_buffer)
                s.send(random_buffer)
                size -= buffer_size
            last_buffer = random_bytes(size)
            hash.update(last_buffer)
            s.send(last_buffer)

            print('XXX warning, sha1sum does not match files XXX')
            print(f"size={orig_size}, sha1sum={hash.hexdigest()}")
        elif option == 1001:
            # Serve a random sized file with random-sized buffers of random bytes, and show the SHA1 hash.
            # This can be verified with: sha1sum filename.
            #
            # header is part of the buffer.
            hash = hashlib.sha1()
            orig_size = random.randint(10_000, 1_000_000)
            size = orig_size

            header_buffer = bytes(f"GETFILE OK {size}\r\n\r\n", "UTF-8")
            header_buffer_size = len(header_buffer)

            payload_size = random.randint(min(100, size), min(1_000, size))
            random_payload = random_bytes(payload_size)

            first_buffer = header_buffer + random_payload
            first_buffer_size = len(first_buffer)

            print(
                f"header size {header_buffer_size} + payload size {payload_size} = first buffer size {first_buffer_size}")

            # Hash only includes the payload, as the header is not stored on the client.
            hash.update(random_payload)
            s.send(first_buffer)

            # Size to send only includes the payload, not the header.
            size -= payload_size
            print(f"remaining size {size}")

            while size > 0:
                buffer_size = random.randint(min(100, size), min(1_000, size))
                random_buffer = bytes([random.randint(0, 255)
                                      for _ in range(0, buffer_size)])
                hash.update(random_buffer)
                s.send(random_buffer)
                size -= buffer_size

            expected_hex = hash.hexdigest()
            print(f"size={orig_size}, sha1sum={expected_hex}")

            # Wait a moment for the client to write the file
            time.sleep(.2)

            # Verify the received file
            try:
                # Get the directory path
                dir_path = os.path.dirname(path)
                if not dir_path:
                    dir_path = '.'

                if not os.path.exists(dir_path):
                    print(f"Directory {dir_path} does not exist")
                    return

                # Get all files and their hashes
                print("Checking files in directory:")
                for filename in os.listdir(dir_path):
                    filepath = os.path.join(dir_path, filename)
                    if os.path.isfile(filepath):
                        try:
                            with open(filepath, 'rb') as f:
                                file_hash = hashlib.sha1()
                                while True:
                                    data = f.read(8192)
                                    if not data:
                                        break
                                    file_hash.update(data)
                                file_hashes[filename] = file_hash.hexdigest()
                        except Exception:
                            continue

                # Check for matching hash
                found_match = False
                for filename, file_hash in file_hashes.items():
                    if file_hash == expected_hex:
                        print(
                            f"File verification successful! Found matching file: {filename}")
                        found_match = True
                        break

                if not found_match:
                    print(
                        f"File verification failed! No file found with SHA1: {expected_hex}")
            except Exception as e:
                print(f"Error verifying file: {e}")
        else:
            print(f"DEBUG: Option {option} not handled, no response sent")
            # Serve a random sized file with random-sized buffers of random bytes, and show the SHA1 hash.
            # This can be verified with: sha1sum filename.
            #
            # header is not part of the buffer.
            hash = hashlib.sha1()
            orig_size = random.randint(10_000, 1_000_000)
            size = orig_size

            # Randomly choose between sending a failure header or the file
            if random.random() < 0.2:
                # Send a random failure header
                failures = [
                    b"GETFILE FILE_NOT_FOUND\r\n\r\n",
                    b"GETFILE ERROR\r\n\r\n",
                    b"GETFILE INVALID\r\n\r\n",
                    b"GETFILE WRONG\r\n\r\n"
                ]
                s.send(random.choice(failures))
            else:
                # Send the full file
                s.send(bytes(f"GETFILE OK {size}\r\n\r\n", "UTF-8"))
                while size > 0:
                    buffer_size = random.randint(
                        min(100, size), min(1_000, size))
                    random_buffer = random_bytes(buffer_size)
                    hash.update(random_buffer)
                    s.send(random_buffer)
                    size -= buffer_size

                print(f"size={orig_size}, sha1sum={hash.hexdigest()}")
    finally:
        s.close()


if __name__ == "__main__":
    file_hashes = {}

    # Which option to test
    option = int(sys.argv[1]) if len(sys.argv) > 1 else -1
    print(f"option={option}")

    ss = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    ss.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # support ipv6
    ss.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    ss.bind(("::", 29483))
    ss.listen(4096)

    # Create a thread pool with a "reasonable" number of worker threads
    with ThreadPoolExecutor(max_workers=100) as executor:
        while True:
            s, t = ss.accept()
            print(f"Accepted connection from {t}")

            # Submit the connection to the thread pool
            executor.submit(handle_connection, s, option, file_hashes)
