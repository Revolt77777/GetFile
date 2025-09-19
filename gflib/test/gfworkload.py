# Workload generator
# Creates content.txt, workload.txt, and files.

import random

SERVER_ROOT = "server_root/random"
PREFIX = "workload/random"

def generate_files(nfiles, min, max):
    with open("workload.txt", "w") as f:
        for i in range(0, nfiles):
            f.write(f"/{PREFIX}{i}\n")

    with open("content.txt", "w") as f:
        for i in range(0, nfiles):
            f.write(f"/{PREFIX}{i} {SERVER_ROOT}/{i}.bin\n")

    buffer_size = 4096
    for i in range(0, nfiles):
        with open(f"{SERVER_ROOT}/{i}.bin", "wb") as f:
            size = random.randint(min, max)

            # A text pattern that is easy to view to see if correct.
            pattern = b'0123456789abcdef0123456789abcde\n'
            for _ in range(0, size // buffer_size):
                # f.write(np.random.bytes(buffer_size))
                f.write(pattern * (buffer_size // len(pattern)))

            remaining = size % buffer_size
            if remaining > 0:
                # f.write(np.random.bytes(remaining))
                f.write(pattern * (remaining // len(pattern)))
                f.write(pattern[0:(remaining % len(pattern))])


if __name__ == '__main__':
    generate_files(10, 32768, 32768*2)
