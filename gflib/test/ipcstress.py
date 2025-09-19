#!/usr/bin/python3

""" IPC Stress Test """

from typing import List, Tuple
import threading
import queue
import signal
import atexit

import os
import shutil
import sys
import glob
import subprocess
import time
import re

# gfclient_download maximum request count
MAX_GFCLIENT_DOWNLOAD_REQUEST_COUNT = 1000

# Block size for the dd command.
DD_BLOCK_SIZE = 8

# Use some powers of two plus some multiple of the dd block size,
# to make generation reasonably fast.
#
# Bytes per second estimation is only available if request count is an even multiple of
# the workload sizes, thus the 10 sizes here.
# Note: A non-existent filename was added to the workload file, so all
# request counts were changed to multiples of 11.
WORKLOAD_SIZES = [
    0,
    568,
    525,
    501,
    369,
    1024 + 1 * DD_BLOCK_SIZE,
    4096 + 7 * DD_BLOCK_SIZE,
    65536 + 13 * DD_BLOCK_SIZE,
    262144 + 19 * DD_BLOCK_SIZE,
    1048576 + 23 * DD_BLOCK_SIZE,
    4 * 1048576 + 29 * DD_BLOCK_SIZE,
    8 * 1048576 + 31 * DD_BLOCK_SIZE,
    16 * 1048576 + 33 * DD_BLOCK_SIZE,
]

# Alternative: random sizes

# For locals.txt, for simplecached:
WORKLOAD_LOCAL_PATH = 'ipcstress_files'

# For workload.txt, for gfclient_download to store:
WORKLOAD_URL_PATH = 'ipcstress'

LOCALS_FILENAME = 'locals-ipcstress.txt'
WORKLOAD_FILENAME = 'workload-ipcstress.txt'

# Minimum size of the shared memory to use in the tests
# This value has been know to change from semester to semester
MIN_SEG_SIZE = 824

# Global variables to track subprocesses for cleanup
active_processes = []
cleanup_lock = threading.Lock()


def cleanup_processes():
    """Terminate all active subprocesses."""
    with cleanup_lock:
        for process in active_processes:
            if process and process.poll() is None:
                try:
                    process.terminate()
                    # Give it a moment to terminate gracefully
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    try:
                        process.kill()
                        process.wait()
                    except:
                        pass
                except:
                    pass
        active_processes.clear()


def signal_handler(signum, frame):
    """Handle termination signals."""
    print(f"\nReceived signal {signum}, terminating subprocesses...")
    cleanup_processes()
    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Register cleanup function to run on exit
atexit.register(cleanup_processes)


def output_reader(process_name: str, stream, output_queue: queue.Queue):
    """Read output from a stream and put it in the queue with process name prepended."""
    for line in iter(stream.readline, ''):
        if line:
            output_queue.put(f"[{process_name}] {line.rstrip()}")


def run_sha1sum(filenames: List[str], output_file: str) -> None:
    """ Run sha1sum on filenames and write to an output file. """
    # Get the hashes. SHA1 is good enough for this.
    result = subprocess.run(
        ['/usr/bin/sha1sum'] + filenames,
        capture_output=True,
        check=True)

    # Store the hashes.
    with open(output_file, 'wb') as file:
        file.write(result.stdout)


def create_arbitrary_size_workload(workdir: str, sizes: List[int]):
    """ Create workload with files of arbitrary exact sizes. """

    # convert workdir to absolute path
    if not os.path.isabs(workdir):
        workdir = os.path.abspath(workdir)

    # Create path or ignore if already present.
    path = f'{workdir}/{WORKLOAD_LOCAL_PATH}'
    os.makedirs(path, exist_ok=True)

    # Create the files with random content at exact sizes.
    filenames = []
    print('Creating workload data files with exact sizes:')
    for i, size in enumerate(sizes):
        filename = f'{path}/workload{i}.bin'
        filenames.append(filename)

        if not os.path.isfile(filename):
            # Create file with exact size using Python
            with open(filename, 'wb') as f:
                if size > 0:
                    # Generate random data in chunks to avoid memory issues with large files
                    chunk_size = min(size, 8192)  # 8KB chunks
                    remaining = size
                    while remaining > 0:
                        current_chunk = min(chunk_size, remaining)
                        random_data = os.urandom(current_chunk)
                        f.write(random_data)
                        remaining -= current_chunk
            print(f"Created {filename} with exact size {size} bytes")

    full_sha1sum_filename = f'{path}/sha1sum.txt'
    print(f'Creating SHA1 hash file: {full_sha1sum_filename}')
    run_sha1sum(filenames, full_sha1sum_filename)

    # Create the locals file.
    full_locals_filename = f'{workdir}/{LOCALS_FILENAME}'
    print(f'Creating locals file: {full_locals_filename}')
    with open(full_locals_filename, 'w') as file:
        for i, filename in enumerate(filenames):
            file.write(f'/{WORKLOAD_URL_PATH}/workload{i}.bin {filename}\n')

    # Create the workload file.
    full_workload_filename = f'{workdir}/{WORKLOAD_FILENAME}'
    print(f'Creating workload file: {full_workload_filename}')
    with open(f'{workdir}/{WORKLOAD_FILENAME}', 'w') as file:
        for i, _ in enumerate(filenames):
            file.write(f'/{WORKLOAD_URL_PATH}/workload{i}.bin\n')
        file.write(f'/{WORKLOAD_URL_PATH}/workload_FNF.bin\n')

    # Delete the result directory if it exists, gfclient_download will recreate it.
    shutil.rmtree(f'{workdir}/{WORKLOAD_URL_PATH}', ignore_errors=True)


def create_workload(workdir: str):
    """ Create workload using the original WORKLOAD_SIZES. """
    create_arbitrary_size_workload(workdir, WORKLOAD_SIZES)


def read_cpu_times(pid: int) -> Tuple[int, int]:
    """ Read utime (user time) and stime (system/kernel time) for a PID, in ticks. """
    with open(f'/proc/{pid}/stat', 'r') as file:
        entries = file.readline().rstrip().split(' ')
        return int(entries[13]), int(entries[14])


def run_ipcstress(
    workdir: str,
    cache_thread_count: int,
    proxy_thread_count: int,
    proxy_segment_count: int,
    proxy_segment_size: int,
    download_thread_count: int,
    request_count: int,
    port: int
) -> int:
    """ Run IPC Stress. Return 0 for normal exit. """

    # Compute the ticks per second
    result = subprocess.run(['/usr/bin/getconf', 'CLK_TCK'],
                            capture_output=True, check=True)
    ticks_per_second = int(result.stdout)

    remaining_request_count = request_count

    # Create output queue for process output
    output_queue = queue.Queue()
    output_threads = []

    popen_cache = subprocess.Popen([
        f'{os.getcwd()}/simplecached',
        '-c',
        f'./{LOCALS_FILENAME}',
        '-t',
        str(cache_thread_count)
    ], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True
    )

    # Add to global process list for cleanup
    with cleanup_lock:
        active_processes.append(popen_cache)

    # Start output reader threads for cache
    cache_stdout_thread = threading.Thread(
        target=output_reader, args=("CACHE", popen_cache.stdout, output_queue))
    cache_stderr_thread = threading.Thread(
        target=output_reader, args=("CACHE", popen_cache.stderr, output_queue))
    cache_stdout_thread.daemon = True
    cache_stderr_thread.daemon = True
    cache_stdout_thread.start()
    cache_stderr_thread.start()
    output_threads.extend([cache_stdout_thread, cache_stderr_thread])

    popen_proxy = subprocess.Popen([
        f'{os.getcwd()}/webproxy',
        '-n',
        str(proxy_segment_count),
        '-p',
        str(port),
        '-t',
        str(proxy_thread_count),
        '-z',
        str(proxy_segment_size)
    ], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True
    )

    # Add to global process list for cleanup
    with cleanup_lock:
        active_processes.append(popen_proxy)

    # Start output reader threads for proxy
    proxy_stdout_thread = threading.Thread(
        target=output_reader, args=("PROXY", popen_proxy.stdout, output_queue))
    proxy_stderr_thread = threading.Thread(
        target=output_reader, args=("PROXY", popen_proxy.stderr, output_queue))
    proxy_stdout_thread.daemon = True
    proxy_stderr_thread.daemon = True
    proxy_stdout_thread.start()
    proxy_stderr_thread.start()
    output_threads.extend([proxy_stdout_thread, proxy_stderr_thread])

    # Give the proxy a quarter second to start, to eliminate the client message:
    # Failed to connect.  Trying again....
    time.sleep(0.250)

    actual_request_done = 0
    popen_download = None
    download_poll = None
    download_output_threads = []

    # Benchmarking:
    start_time = None
    start_cache_utime, start_cache_stime = read_cpu_times(popen_cache.pid)
    start_proxy_utime, start_proxy_stime = read_cpu_times(popen_proxy.pid)

    # Summary for the end.
    total_elapsed_time = 0
    total_elapsed_cache_utime = 0
    total_elapsed_cache_stime = 0
    total_elapsed_proxy_utime = 0
    total_elapsed_proxy_stime = 0

    # Output processing thread
    def process_output():
        while True:
            try:
                line = output_queue.get(timeout=0.1)
                print(line)
                output_queue.task_done()
            except queue.Empty:
                # Check if all processes are still running
                if (popen_cache.poll() is not None and
                    popen_proxy.poll() is not None and
                        (popen_download is None or popen_download.poll() is not None)):
                    break

    output_processor = threading.Thread(target=process_output)
    output_processor.daemon = True
    output_processor.start()

    # print(f'download pid: {popen_download.pid}')
    while True:
        if popen_download:
            download_poll = popen_download.poll()

        # Download if first time or previous request complete.
        # explicit "is not None" is needed because the return code may be 0
        if (download_poll is not None) or not popen_download:
            if start_time:
                elapsed_time = time.time() - start_time
                total_elapsed_time += elapsed_time

                # Requests per second
                rps = actual_request_count / elapsed_time
                actual_request_done += actual_request_count

                # CPU time (user and system)
                cache_utime, cache_stime = read_cpu_times(popen_cache.pid)
                proxy_utime, proxy_stime = read_cpu_times(popen_proxy.pid)
                elapsed_cache_utime = (
                    cache_utime - start_cache_utime) / ticks_per_second
                elapsed_cache_stime = (
                    cache_stime - start_cache_stime) / ticks_per_second
                elapsed_proxy_utime = (
                    proxy_utime - start_proxy_utime) / ticks_per_second
                elapsed_proxy_stime = (
                    proxy_stime - start_proxy_stime) / ticks_per_second
                (start_cache_utime, start_cache_stime) = (
                    cache_utime, cache_stime)
                (start_proxy_utime, start_proxy_stime) = (
                    proxy_utime, proxy_stime)

                elapsed_cache_ttime = elapsed_cache_utime + elapsed_cache_stime
                elapsed_proxy_ttime = elapsed_proxy_utime + elapsed_proxy_stime

                # For the summary:
                total_elapsed_cache_utime += elapsed_cache_utime
                total_elapsed_cache_stime += elapsed_cache_stime
                total_elapsed_proxy_utime += elapsed_proxy_utime
                total_elapsed_proxy_stime += elapsed_proxy_stime

                # bps is only possible if the requests are a multiple of the workload.
                # Otherwise, gfclient_download does not evenly distribute the requests
                # across the workload files.
                request_count_chunk, request_count_extra = divmod(
                    actual_request_count, len(WORKLOAD_SIZES))
                if not request_count_extra:
                    nbytes = request_count_chunk * sum(WORKLOAD_SIZES)
                    bps = nbytes / elapsed_time
                    print(
                        f'{actual_request_done}/{request_count} in {elapsed_time:0.2f}s, {rps:0.2f} rps, {bps:0.0f} bps, ',
                        end=''
                    )
                else:
                    print(
                        f'{actual_request_done}/{request_count} in {elapsed_time:0.2f}s, {rps:0.2f} rps, ',
                        end=''
                    )

                print(
                    'cache: '
                    f'{elapsed_cache_utime}s {100 * elapsed_cache_utime / elapsed_time:0.2f}% user, '
                    f'{elapsed_cache_stime}s {100 * elapsed_cache_stime / elapsed_time:0.2f}% kernel, '
                    f'{elapsed_cache_ttime}s {100 * elapsed_cache_ttime / elapsed_time:0.2f}% total, '
                    'proxy: '
                    f'{elapsed_proxy_utime}s {100 * elapsed_proxy_utime / elapsed_time:0.2f}% user, '
                    f'{elapsed_proxy_stime}s {100 * elapsed_proxy_stime / elapsed_time:0.2f}% kernel, '
                    f'{elapsed_proxy_ttime}s {100 * elapsed_proxy_ttime / elapsed_time:0.2f}% total'
                )

            if remaining_request_count == 0:
                break

            actual_request_count = min(
                MAX_GFCLIENT_DOWNLOAD_REQUEST_COUNT, remaining_request_count)

            popen_download = subprocess.Popen([
                f'{os.getcwd()}/gfclient_download',
                '-p',
                str(port),
                '-t',
                str(download_thread_count),
                '-w',
                f'./{WORKLOAD_FILENAME}',
                '-r',
                str(actual_request_count)
            ], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True
            )

            # Add to global process list for cleanup
            with cleanup_lock:
                active_processes.append(popen_download)

            # Start output reader threads for download
            download_stdout_thread = threading.Thread(target=output_reader, args=(
                "DOWNLOAD", popen_download.stdout, output_queue))
            download_stderr_thread = threading.Thread(target=output_reader, args=(
                "DOWNLOAD", popen_download.stderr, output_queue))
            download_stdout_thread.daemon = True
            download_stderr_thread.daemon = True
            download_stdout_thread.start()
            download_stderr_thread.start()
            download_output_threads.extend(
                [download_stdout_thread, download_stderr_thread])

            remaining_request_count -= actual_request_count
            start_time = time.time()

        cache_poll = popen_cache.poll()
        proxy_poll = popen_proxy.poll()

        if (cache_poll is not None) and (proxy_poll is not None):
            print(
                f'Both cache exited ({cache_poll}) and proxy ({proxy_poll}) exited')
            if popen_download:
                popen_download.terminate()
            return 3
        if cache_poll is not None:
            print(f'Cache exited ({cache_poll})')
            if popen_download:
                popen_download.terminate()
            popen_proxy.terminate()
            return 1
        if proxy_poll is not None:
            print(f'Proxy exited ({proxy_poll})')
            if popen_download:
                popen_download.terminate()
            popen_cache.terminate()
            return 2

        time.sleep(1)

    popen_cache.terminate()
    popen_proxy.terminate()

    # Benchmark for this run, if it ran more than once
    if total_elapsed_time > 0:
        rps = actual_request_done / total_elapsed_time
        total_elapsed_cache_ttime = total_elapsed_cache_utime + total_elapsed_cache_stime
        total_elapsed_proxy_ttime = total_elapsed_proxy_utime + total_elapsed_proxy_stime

        request_count_chunk, request_count_extra = divmod(
            actual_request_done, len(WORKLOAD_SIZES))
        if not request_count_extra:
            nbytes = request_count_chunk * sum(WORKLOAD_SIZES)
            bps = nbytes / total_elapsed_time
            print(
                f'Summary: {total_elapsed_time:0.2f}s, {rps:0.2f} rps, {bps:0.0f} bps, ',
                end=''
            )
        else:
            print(
                f'Summary: {total_elapsed_time:0.2f}s, {rps:0.2f} rps, ',
                end=''
            )

        print(
            'cache: '
            f'{total_elapsed_cache_utime}s {100 * total_elapsed_cache_utime / total_elapsed_time:0.2f}% user, '
            f'{total_elapsed_cache_stime}s {100 * total_elapsed_cache_stime / total_elapsed_time:0.2f}% kernel, '
            f'{total_elapsed_cache_ttime}s {100 * total_elapsed_cache_ttime / total_elapsed_time:0.2f}% total, '
            'proxy: '
            f'{total_elapsed_proxy_utime}s {100 * total_elapsed_proxy_utime / total_elapsed_time:0.2f}% user, '
            f'{total_elapsed_proxy_stime}s {100 * total_elapsed_proxy_stime / total_elapsed_time:0.2f}% kernel, '
            f'{total_elapsed_proxy_ttime}s {100 * total_elapsed_proxy_ttime / total_elapsed_time:0.2f}% total'
        )

    # Clean up processes from global list
    cleanup_processes()

    return 0


def verify_results(workdir: str) -> bool:
    """ Verify results, return True on success. """
    filenames = glob.glob(f'{workdir}/{WORKLOAD_URL_PATH}/*')
    result_filename = f'{workdir}/{WORKLOAD_URL_PATH}/sha1sum-result.txt'
    run_sha1sum(filenames, result_filename)

    # Entries in the sha1sum files are full paths.
    re_sha1sum = re.compile(r'(\w+)\s+(.*)')

    # Load the original hashes for comparison.
    workload_sha1 = {}
    with open(f'{workdir}/{WORKLOAD_LOCAL_PATH}/sha1sum.txt', 'r') as file:
        for line in file:
            match = re_sha1sum.match(line.rstrip())
            if match:
                workload_sha1[os.path.basename(
                    match.group(2))] = match.group(1)

    # Find all the mismatching hashes.
    success = True
    with open(result_filename, 'r') as file:
        for line in file:
            match = re_sha1sum.match(line.rstrip())
            if match:
                filename = os.path.basename(match.group(2))
                workload_hash = workload_sha1.get(filename)
                if workload_hash and (workload_hash != match.group(1)):
                    print(f'Hash mismatch: {filename}')
                    success = False

    return success


def run_base_test(workdir: str):
    """ Base level of testing. """

    port = 10823
    create_workload(workdir)

    proxy_segment_size = 1024
    download_thread_count = 1
    request_count = 110
    cache_thread_count = 1
    proxy_thread_count = 1
    proxy_segment_count = 1

    print(
        f'cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
        f'download_thread_count={download_thread_count}, request_count={request_count}'
    )
    if run_ipcstress(
        workdir,
        cache_thread_count,
        proxy_thread_count,
        proxy_segment_count,
        proxy_segment_size,
        download_thread_count,
        request_count,
        port
    ) != 0:
        return

    if not verify_results(workdir):
        return


def run_parameter_test(workdir: str):
    """ Test through a wide range of parameters. """

    port = 10823
    create_workload(workdir)

    request_count = 10
    for cache_thread_count in range(1, 101, 10):
        for proxy_thread_count in range(cache_thread_count, 101, 10):
            for proxy_segment_count in range(1, 101, 10):
                download_thread_count = proxy_thread_count

                proxy_segment_size = MIN_SEG_SIZE
                while proxy_segment_size <= 1048576:
                    print(
                        f'cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
                        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
                        f'download_thread_count={download_thread_count}, request_count={request_count}'
                    )

                    if run_ipcstress(
                        workdir,
                        cache_thread_count,
                        proxy_thread_count,
                        proxy_segment_count,
                        proxy_segment_size,
                        download_thread_count,
                        request_count,
                        port
                    ) != 0:
                        return

                    if not verify_results(workdir):
                        return

                    proxy_segment_size *= 4


def run_stress_test(workdir: str):
    """ Stress test with fixed proxy segment size and number of segments. """

    port = 10823
    create_workload(workdir)

    request_count = 10
    proxy_segment_count = 50
    proxy_segment_size = 1048576

    for cache_thread_count in range(20, 101, 10):
        for proxy_thread_count in range(cache_thread_count, 101, 10):
            download_thread_count = proxy_thread_count

            print(
                f'cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
                f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
                f'download_thread_count={download_thread_count}, request_count={request_count}'
            )

            if run_ipcstress(
                workdir,
                cache_thread_count,
                proxy_thread_count,
                proxy_segment_count,
                proxy_segment_size,
                download_thread_count,
                request_count,
                port
            ) != 0:
                return

            if not verify_results(workdir):
                return


def run_soak_test(workdir: str):
    """ Soak test with fixed parameters. """

    port = 10823
    create_workload(workdir)

    request_count = 1000000
    proxy_segment_count = 50
    proxy_segment_size = 1048576

    cache_thread_count = 100
    proxy_thread_count = 100
    download_thread_count = proxy_thread_count

    print(
        f'cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
        f'download_thread_count={download_thread_count}, request_count={request_count}'
    )

    if run_ipcstress(
        workdir,
        cache_thread_count,
        proxy_thread_count,
        proxy_segment_count,
        proxy_segment_size,
        download_thread_count,
        request_count,
        port
    ) != 0:
        return

    if not verify_results(workdir):
        return


def run_debug_test(workdir: str):
    """ Debug test with just the first few files. """

    port = 10823
    create_arbitrary_size_workload(workdir, WORKLOAD_SIZES[:4])

    proxy_segment_size = 1024
    download_thread_count = 1
    request_count = 4  # Just test workload0-3
    cache_thread_count = 1
    proxy_thread_count = 1
    proxy_segment_count = 1

    print(
        f'DEBUG TEST: cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
        f'download_thread_count={download_thread_count}, request_count={request_count}'
    )
    if run_ipcstress(
        workdir,
        cache_thread_count,
        proxy_thread_count,
        proxy_segment_count,
        proxy_segment_size,
        download_thread_count,
        request_count,
        port
    ) != 0:
        return

    if not verify_results(workdir):
        return


def run_ipcstress_multi_proxy(
    workdir: str,
    cache_thread_count: int,
    proxy_thread_count: int,
    proxy_segment_count: int,
    proxy_segment_size: int,
    download_thread_count: int,
    request_count: int,
    base_port: int,
    num_proxies: int
) -> int:
    """ Run IPC Stress with multiple proxies for one cache. Return 0 for normal exit. """

    # Compute the ticks per second
    result = subprocess.run(['/usr/bin/getconf', 'CLK_TCK'],
                            capture_output=True, check=True)
    ticks_per_second = int(result.stdout)

    remaining_request_count = request_count

    # Create output queue for process output
    output_queue = queue.Queue()
    output_threads = []

    # Start the cache process
    popen_cache = subprocess.Popen([
        f'{os.getcwd()}/simplecached',
        '-c',
        f'./{LOCALS_FILENAME}',
        '-t',
        str(cache_thread_count)
    ], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True
    )

    # Add to global process list for cleanup
    with cleanup_lock:
        active_processes.append(popen_cache)

    # Start output reader threads for cache
    cache_stdout_thread = threading.Thread(
        target=output_reader, args=("CACHE", popen_cache.stdout, output_queue))
    cache_stderr_thread = threading.Thread(
        target=output_reader, args=("CACHE", popen_cache.stderr, output_queue))
    cache_stdout_thread.daemon = True
    cache_stderr_thread.daemon = True
    cache_stdout_thread.start()
    cache_stderr_thread.start()
    output_threads.extend([cache_stdout_thread, cache_stderr_thread])

    # Start multiple proxy processes
    proxy_processes = []
    proxy_ports = []
    for i in range(num_proxies):
        port = base_port + i
        proxy_ports.append(port)

        popen_proxy = subprocess.Popen([
            f'{os.getcwd()}/webproxy',
            '-n',
            str(proxy_segment_count),
            '-p',
            str(port),
            '-t',
            str(proxy_thread_count),
            '-z',
            str(proxy_segment_size)
        ], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True
        )

        proxy_processes.append(popen_proxy)

        # Add to global process list for cleanup
        with cleanup_lock:
            active_processes.append(popen_proxy)

        # Start output reader threads for each proxy
        proxy_stdout_thread = threading.Thread(
            target=output_reader, args=(f"PROXY{i}", popen_proxy.stdout, output_queue))
        proxy_stderr_thread = threading.Thread(
            target=output_reader, args=(f"PROXY{i}", popen_proxy.stderr, output_queue))
        proxy_stdout_thread.daemon = True
        proxy_stderr_thread.daemon = True
        proxy_stdout_thread.start()
        proxy_stderr_thread.start()
        output_threads.extend([proxy_stdout_thread, proxy_stderr_thread])

    # Give the proxies a quarter second to start
    time.sleep(0.250)

    actual_request_done = 0
    download_processes = []
    download_output_threads = []

    # Benchmarking:
    start_time = None
    start_cache_utime, start_cache_stime = read_cpu_times(popen_cache.pid)

    # Track CPU times for all proxies
    start_proxy_times = []
    for proxy in proxy_processes:
        utime, stime = read_cpu_times(proxy.pid)
        start_proxy_times.append((utime, stime))

    # Summary for the end.
    total_elapsed_time = 0
    total_elapsed_cache_utime = 0
    total_elapsed_cache_stime = 0
    total_elapsed_proxy_utime = 0
    total_elapsed_proxy_stime = 0

    # Output processing thread
    def process_output():
        while True:
            try:
                line = output_queue.get(timeout=0.1)
                print(line)
                output_queue.task_done()
            except queue.Empty:
                # Check if all processes are still running
                all_proxies_done = all(
                    proxy.poll() is not None for proxy in proxy_processes)
                all_downloads_done = all(
                    download.poll() is not None for download in download_processes)
                if (popen_cache.poll() is not None and all_proxies_done and
                        (not download_processes or all_downloads_done)):
                    break

    output_processor = threading.Thread(target=process_output)
    output_processor.daemon = True
    output_processor.start()

    current_proxy_index = 0

    while True:
        # Check if all downloads are complete
        all_downloads_complete = all(
            download.poll() is not None for download in download_processes)

        # Download if first time or previous requests complete.
        if (not download_processes) or all_downloads_complete:
            if start_time:
                elapsed_time = time.time() - start_time
                total_elapsed_time += elapsed_time

                # Requests per second
                rps = actual_request_count / elapsed_time
                actual_request_done += actual_request_count

                # CPU time (user and system)
                cache_utime, cache_stime = read_cpu_times(popen_cache.pid)
                elapsed_cache_utime = (
                    cache_utime - start_cache_utime) / ticks_per_second
                elapsed_cache_stime = (
                    cache_stime - start_cache_stime) / ticks_per_second
                start_cache_utime, start_cache_stime = cache_utime, cache_stime

                # Sum up CPU times for all proxies
                elapsed_proxy_utime = 0
                elapsed_proxy_stime = 0
                for i, proxy in enumerate(proxy_processes):
                    proxy_utime, proxy_stime = read_cpu_times(proxy.pid)
                    start_utime, start_stime = start_proxy_times[i]
                    elapsed_proxy_utime += (proxy_utime -
                                            start_utime) / ticks_per_second
                    elapsed_proxy_stime += (proxy_stime -
                                            start_stime) / ticks_per_second
                    start_proxy_times[i] = (proxy_utime, proxy_stime)

                elapsed_cache_ttime = elapsed_cache_utime + elapsed_cache_stime
                elapsed_proxy_ttime = elapsed_proxy_utime + elapsed_proxy_stime

                # For the summary:
                total_elapsed_cache_utime += elapsed_cache_utime
                total_elapsed_cache_stime += elapsed_cache_stime
                total_elapsed_proxy_utime += elapsed_proxy_utime
                total_elapsed_proxy_stime += elapsed_proxy_stime

                # bps calculation
                request_count_chunk, request_count_extra = divmod(
                    actual_request_count, len(WORKLOAD_SIZES))
                if not request_count_extra:
                    nbytes = request_count_chunk * sum(WORKLOAD_SIZES)
                    bps = nbytes / elapsed_time
                    print(
                        f'{actual_request_done}/{request_count} in {elapsed_time:0.2f}s, {rps:0.2f} rps, {bps:0.0f} bps, ',
                        end=''
                    )
                else:
                    print(
                        f'{actual_request_done}/{request_count} in {elapsed_time:0.2f}s, {rps:0.2f} rps, ',
                        end=''
                    )

                print(
                    'cache: '
                    f'{elapsed_cache_utime}s {100 * elapsed_cache_utime / elapsed_time:0.2f}% user, '
                    f'{elapsed_cache_stime}s {100 * elapsed_cache_stime / elapsed_time:0.2f}% kernel, '
                    f'{elapsed_cache_ttime}s {100 * elapsed_cache_ttime / elapsed_time:0.2f}% total, '
                    f'proxies({num_proxies}): '
                    f'{elapsed_proxy_utime}s {100 * elapsed_proxy_utime / elapsed_time:0.2f}% user, '
                    f'{elapsed_proxy_stime}s {100 * elapsed_proxy_stime / elapsed_time:0.2f}% kernel, '
                    f'{elapsed_proxy_ttime}s {100 * elapsed_proxy_ttime / elapsed_time:0.2f}% total'
                )

            if remaining_request_count == 0:
                break

            actual_request_count = min(
                MAX_GFCLIENT_DOWNLOAD_REQUEST_COUNT, remaining_request_count)

            # Clear previous download processes
            download_processes = []

            # Distribute requests across proxies
            requests_per_proxy = actual_request_count // num_proxies
            remaining_requests = actual_request_count % num_proxies

            for i, port in enumerate(proxy_ports):
                proxy_requests = requests_per_proxy
                if i < remaining_requests:
                    proxy_requests += 1

                if proxy_requests > 0:
                    popen_download = subprocess.Popen([
                        f'{os.getcwd()}/gfclient_download',
                        '-p',
                        str(port),
                        '-t',
                        str(download_thread_count // num_proxies + (1 if i <
                            download_thread_count % num_proxies else 0)),
                        '-w',
                        f'./{WORKLOAD_FILENAME}',
                        '-r',
                        str(proxy_requests)
                    ], cwd=workdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True
                    )

                    download_processes.append(popen_download)

                    # Add to global process list for cleanup
                    with cleanup_lock:
                        active_processes.append(popen_download)

                    # Start output reader threads for download
                    download_stdout_thread = threading.Thread(target=output_reader, args=(
                        f"DOWNLOAD{i}", popen_download.stdout, output_queue))
                    download_stderr_thread = threading.Thread(target=output_reader, args=(
                        f"DOWNLOAD{i}", popen_download.stderr, output_queue))
                    download_stdout_thread.daemon = True
                    download_stderr_thread.daemon = True
                    download_stdout_thread.start()
                    download_stderr_thread.start()
                    download_output_threads.extend(
                        [download_stdout_thread, download_stderr_thread])

            remaining_request_count -= actual_request_count
            start_time = time.time()

        cache_poll = popen_cache.poll()
        any_proxy_exited = any(
            proxy.poll() is not None for proxy in proxy_processes)

        if cache_poll is not None and any_proxy_exited:
            print(
                f'Both cache exited ({cache_poll}) and at least one proxy exited')
            for download in download_processes:
                download.terminate()
            return 3
        if cache_poll is not None:
            print(f'Cache exited ({cache_poll})')
            for download in download_processes:
                download.terminate()
            for proxy in proxy_processes:
                proxy.terminate()
            return 1
        if any_proxy_exited:
            exited_proxies = [i for i, proxy in enumerate(
                proxy_processes) if proxy.poll() is not None]
            print(f'Proxies {exited_proxies} exited')
            for download in download_processes:
                download.terminate()
            popen_cache.terminate()
            return 2

        time.sleep(1)

    popen_cache.terminate()
    for proxy in proxy_processes:
        proxy.terminate()

    # Benchmark summary
    if total_elapsed_time > 0:
        rps = actual_request_done / total_elapsed_time
        total_elapsed_cache_ttime = total_elapsed_cache_utime + total_elapsed_cache_stime
        total_elapsed_proxy_ttime = total_elapsed_proxy_utime + total_elapsed_proxy_stime

        request_count_chunk, request_count_extra = divmod(
            actual_request_done, len(WORKLOAD_SIZES))
        if not request_count_extra:
            nbytes = request_count_chunk * sum(WORKLOAD_SIZES)
            bps = nbytes / total_elapsed_time
            print(
                f'Summary: {total_elapsed_time:0.2f}s, {rps:0.2f} rps, {bps:0.0f} bps, ',
                end=''
            )
        else:
            print(
                f'Summary: {total_elapsed_time:0.2f}s, {rps:0.2f} rps, ',
                end=''
            )

        print(
            'cache: '
            f'{total_elapsed_cache_utime}s {100 * total_elapsed_cache_utime / total_elapsed_time:0.2f}% user, '
            f'{total_elapsed_cache_stime}s {100 * total_elapsed_cache_stime / total_elapsed_time:0.2f}% kernel, '
            f'{total_elapsed_cache_ttime}s {100 * total_elapsed_cache_ttime / total_elapsed_time:0.2f}% total, '
            f'proxies({num_proxies}): '
            f'{total_elapsed_proxy_utime}s {100 * total_elapsed_proxy_utime / total_elapsed_time:0.2f}% user, '
            f'{total_elapsed_proxy_stime}s {100 * total_elapsed_proxy_stime / total_elapsed_time:0.2f}% kernel, '
            f'{total_elapsed_proxy_ttime}s {100 * total_elapsed_proxy_ttime / total_elapsed_time:0.2f}% total'
        )

    # Clean up processes from global list
    cleanup_processes()

    return 0


def run_multi_proxy_test(workdir: str):
    """ Test with multiple proxies for one cache. """

    base_port = 10823
    create_workload(workdir)

    proxy_segment_size = 8192  # Increased for better testing
    download_thread_count = 12  # Increased to ensure multiple threads per proxy
    request_count = 220  # Multiple of 11 for even distribution
    cache_thread_count = 8  # Increased to test multiple cache threads
    proxy_thread_count = 6  # Increased to test multiple proxy threads
    proxy_segment_count = 16  # Increased to test multiple shared memory segments
    num_proxies = 3

    print(
        f'MULTI-PROXY TEST: cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
        f'download_thread_count={download_thread_count}, request_count={request_count}, '
        f'num_proxies={num_proxies}, base_port={base_port}'
    )

    print(
        f'Total threads: Cache={cache_thread_count}, Proxies={num_proxies}x{proxy_thread_count}={num_proxies * proxy_thread_count}, Downloads={download_thread_count}')
    print(f'Shared memory: {proxy_segment_count} segments of {proxy_segment_size} bytes each = {proxy_segment_count * proxy_segment_size} total bytes per proxy')

    if run_ipcstress_multi_proxy(
        workdir,
        cache_thread_count,
        proxy_thread_count,
        proxy_segment_count,
        proxy_segment_size,
        download_thread_count,
        request_count,
        base_port,
        num_proxies
    ) != 0:
        return

    if not verify_results(workdir):
        return


def run_multi_proxy_stress_test(workdir: str):
    """ Stress test with many proxies, threads, and shared memory segments for one cache. """

    base_port = 10823
    create_workload(workdir)

    proxy_segment_size = 16384  # Large segments for stress testing
    download_thread_count = 25  # Many download threads
    request_count = 550  # Multiple of 11 for even distribution
    cache_thread_count = 20  # Many cache threads
    proxy_thread_count = 15  # Many proxy threads per proxy
    proxy_segment_count = 32  # Many shared memory segments
    num_proxies = 5  # More proxies

    print(
        f'MULTI-PROXY STRESS TEST: cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
        f'download_thread_count={download_thread_count}, request_count={request_count}, '
        f'num_proxies={num_proxies}, base_port={base_port}'
    )

    print(
        f'Total threads: Cache={cache_thread_count}, Proxies={num_proxies}x{proxy_thread_count}={num_proxies * proxy_thread_count}, Downloads={download_thread_count}')
    print(f'Shared memory: {proxy_segment_count} segments of {proxy_segment_size} bytes each = {proxy_segment_count * proxy_segment_size} total bytes per proxy')
    print(
        f'Total shared memory across all proxies: {num_proxies * proxy_segment_count * proxy_segment_size} bytes')

    if run_ipcstress_multi_proxy(
        workdir,
        cache_thread_count,
        proxy_thread_count,
        proxy_segment_count,
        proxy_segment_size,
        download_thread_count,
        request_count,
        base_port,
        num_proxies
    ) != 0:
        return

    if not verify_results(workdir):
        return


def create_small_files_workload(workdir: str):
    """ Create workload with only small files under 1KB. """

    # Use only small file sizes (under 1KB) with exact sizes
    small_workload_sizes = [
        0,  
        64, 
        128,
        256,
        369,
        512,
        513,
        523,
        563,
        768,
        1023
    ]

    # Use the new function that can create exact sizes
    create_arbitrary_size_workload(workdir, small_workload_sizes)


def run_small_files_multi_proxy_test(workdir: str):
    """ Test with multiple proxies and clients using only small files under 1KB. """

    base_port = 10823
    create_small_files_workload(workdir)

    proxy_segment_size = 2048 
    download_thread_count = 16
    request_count = 330       
    cache_thread_count = 10   
    proxy_thread_count = 8    
    proxy_segment_count = 12  
    num_proxies = 4           

    print(
        f'SMALL FILES MULTI-PROXY TEST: cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
        f'download_thread_count={download_thread_count}, request_count={request_count}, '
        f'num_proxies={num_proxies}, base_port={base_port}'
    )

    # Calculate small file sizes being used
    small_sizes = [0, 64, 128, 256, 369, 512, 513, 523, 563, 768, 1023]
    total_small_files_size = sum(small_sizes)
    avg_file_size = total_small_files_size / len(small_sizes)

    print(f'Small file sizes: {small_sizes} bytes')
    print(
        f'Average file size: {avg_file_size:.1f} bytes, Max file size: {max(small_sizes)} bytes')
    print(
        f'Total threads: Cache={cache_thread_count}, Proxies={num_proxies}x{proxy_thread_count}={num_proxies * proxy_thread_count}, Downloads={download_thread_count}')
    print(f'Shared memory: {proxy_segment_count} segments of {proxy_segment_size} bytes each = {proxy_segment_count * proxy_segment_size} total bytes per proxy')
    print(f'This test focuses on high concurrency with many small file transfers')

    if run_ipcstress_multi_proxy(
        workdir,
        cache_thread_count,
        proxy_thread_count,
        proxy_segment_count,
        proxy_segment_size,
        download_thread_count,
        request_count,
        base_port,
        num_proxies
    ) != 0:
        return

    if not verify_results(workdir):
        return


def run_single_segment_test(workdir: str):
    """ Test with multiple threads but only one shared memory segment. """

    port = 10823
    create_workload(workdir)

    # Test parameters: multiple threads, single shared memory segment
    cache_thread_count = 1    
    proxy_thread_count = 11   
    proxy_segment_count = 1   
    proxy_segment_size = 824  
    download_thread_count = 11
    request_count = 11        

    print(
        f'SINGLE SEGMENT TEST: cache_thread_count={cache_thread_count}, proxy_thread_count={proxy_thread_count}, '
        f'proxy_segment_count={proxy_segment_count}, proxy_segment_size={proxy_segment_size}, '
        f'download_thread_count={download_thread_count}, request_count={request_count}'
    )

    print(f'This test focuses on thread contention with only ONE shared memory segment')
    print(
        f'Multiple proxy threads ({proxy_thread_count}) and download threads ({download_thread_count}) must share a single {proxy_segment_size}-byte segment')
    print(f'This creates a bottleneck to test synchronization and thread safety')

    if run_ipcstress(
        workdir,
        cache_thread_count,
        proxy_thread_count,
        proxy_segment_count,
        proxy_segment_size,
        download_thread_count,
        request_count,
        port
    ) != 0:
        return

    if not verify_results(workdir):
        return


if __name__ == '__main__':
    test_names = []
    for name in list(globals().keys()):
        if name.startswith('run_') and name.endswith("_test"):
            test_name = name[4:-5]
            test_names.append(test_name)

    print(f'python3 {sys.argv[0]} workdir {test_names}')
    workdir = sys.argv[1] if len(sys.argv) >= 2 else '.'
    test_name = sys.argv[2] if len(sys.argv) >= 3 else 'base'

    test_function_name = f'run_{test_name}_test'
    if test_function_name in globals():
        (globals()[test_function_name])(workdir)
    else:
        print(f"Test '{test_name}' not found. Available tests: {test_names}")
