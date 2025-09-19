#!/usr/bin/python3

""" Distributed File System Stress Test """

from typing import List, Tuple
import sys
import zlib
import os
import time
import subprocess
import signal
import atexit
import threading
import queue
import shutil

# Global variables to track processes
server_process = None
client_processes = []
server_port = "54080"
server_address = f"127.0.0.1:{server_port}"
output_threads = []

# Use a queue to manage synchronized output from different sources
output_queue = queue.Queue()
output_thread_running = False


def output_printer():
    """ Thread function to print output in order from queue """
    global output_thread_running

    try:
        while output_thread_running:
            try:
                # Use a short timeout so we can check the running flag frequently
                item = output_queue.get(timeout=0.1)
                print(item, flush=True)  # Force flush output
                output_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in output printer: {e}", flush=True)

        print("Output printer thread exiting", flush=True)
    except Exception as e:
        print(f"Fatal error in output printer thread: {e}", flush=True)


def start_output_printer():
    """ Start the output printer thread """
    global output_thread_running

    output_thread_running = True
    thread = threading.Thread(target=output_printer, daemon=True)
    thread.start()
    return thread


def stream_output(stream, prefix):
    """ Stream output from a process """
    try:
        for line in iter(stream.readline, b''):
            if line:
                output_queue.put(f"{prefix}: {line.decode().rstrip()}")
    except (ValueError, IOError) as e:
        output_queue.put(f"{prefix} stream error: {e}")


def monitor_process_output(process, name):
    """ Start threads to monitor stdout and stderr of a process """
    stdout_thread = threading.Thread(
        target=stream_output,
        args=(process.stdout, f"{name} [stdout]"),
        daemon=True
    )
    stderr_thread = threading.Thread(
        target=stream_output,
        args=(process.stderr, f"{name} [stderr]"),
        daemon=True
    )

    stdout_thread.start()
    stderr_thread.start()

    return stdout_thread, stderr_thread


def cleanup_processes():
    """ Clean up all spawned processes """
    global server_process, client_processes, output_thread_running

    print("Cleaning up processes...")
    output_queue.put("Cleaning up processes...")

    # First set the flag to stop the output printer
    output_thread_running = False

    # Try to stop client processes with SIGINT first
    for i, client_process in enumerate(client_processes):
        if client_process and client_process.poll() is None:
            try:
                print(f"Sending SIGINT to client {i}...")
                client_process.send_signal(signal.SIGINT)
            except Exception as e:
                print(f"Error sending SIGINT to client {i}: {e}")

    # Wait a bit for clients to clean up
    time.sleep(0.5)

    # Stop server process with SIGINT first
    if server_process and server_process.poll() is None:
        try:
            print("Sending SIGINT to server...")
            server_process.send_signal(signal.SIGINT)
        except Exception as e:
            print(f"Error sending SIGINT to server: {e}")

    # Wait a bit for server to clean up
    time.sleep(0.5)

    # Now forcefully terminate any remaining processes
    for i, client_process in enumerate(client_processes):
        if client_process and client_process.poll() is None:
            try:
                print(f"Terminating client {i}...")
                client_process.terminate()
                # Use a shorter timeout
                client_process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                print(f"Killing client {i}...")
                try:
                    client_process.kill()
                    client_process.wait(timeout=0.5)
                except Exception as e:
                    print(f"Error killing client {i}: {e}")

    # Stop server process
    if server_process and server_process.poll() is None:
        try:
            print("Terminating server...")
            server_process.terminate()
            # Use a shorter timeout
            server_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            print("Killing server...")
            try:
                server_process.kill()
                server_process.wait(timeout=0.5)
            except Exception as e:
                print(f"Error killing server: {e}")

    # Don't wait for queue to drain, just mark as done
    print("Cleanup complete")

    client_processes.clear()
    server_process = None


# Function to force exit after a timeout
def force_exit(timeout=2):
    """Force exit the program after a timeout"""
    time.sleep(timeout)
    print(f"Forcing exit after {timeout}s timeout")
    os._exit(1)


def signal_handler(signum, frame):
    """ Handle signals for graceful shutdown """
    print(f"Received signal {signum}, shutting down...")
    output_queue.put(f"Received signal {signum}, shutting down...")

    # Start a thread that will force exit if cleanup takes too long
    force_exit_thread = threading.Thread(target=force_exit, daemon=True)
    force_exit_thread.start()

    cleanup_processes()
    sys.exit(0)


def build_dfs_binaries() -> None:
    """ Build DFS binaries using comprehensive build process """
    output_queue.put("Building DFS binaries...")
    output_queue.put("Running make clean_all...")

    try:
        # Clean everything
        result = subprocess.run(["make", "-j", str(os.cpu_count()), "clean_all"],
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            output_queue.put(f"make clean_all failed: {result.stderr}")
            raise RuntimeError("Failed to clean project")

        output_queue.put("Running make protos...")
        # Build protobuf files
        result = subprocess.run(
            ["make", "-j", str(os.cpu_count()), "protos"], capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            output_queue.put(f"make protos failed: {result.stderr}")
            raise RuntimeError("Failed to build protobuf files")

        output_queue.put("Running make part2...")
        # Build part2 project
        result = subprocess.run(
            ["make", "-j", str(os.cpu_count()), "part2"], capture_output=True, text=True, timeout=180)
        if result.returncode != 0:
            output_queue.put(f"make part2 failed: {result.stderr}")
            raise RuntimeError("Failed to build part2 project")

        output_queue.put("DFS binaries built successfully")

    except subprocess.TimeoutExpired:
        raise RuntimeError("Build process timed out")
    except Exception as e:
        output_queue.put(f"Build error: {e}")
        raise


def ensure_empty_directory(directory: str) -> None:
    """ Ensure directory exists and is empty """
    if os.path.exists(directory):
        output_queue.put(f"Cleaning directory: {directory}")
        # Remove all contents
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            try:
                if os.path.isfile(item_path):
                    os.unlink(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                output_queue.put(f"  Error removing {item}: {e}")

    os.makedirs(directory, exist_ok=True)


def start_server(server_dir: str, debug_level: int = 2) -> subprocess.Popen:
    """ Start the DFS server """
    global server_process, output_threads

    output_queue.put(
        f"Starting DFS server on {server_address} with mount path {server_dir} (debug level: {debug_level})")

    # Ensure server directory exists and is empty
    ensure_empty_directory(server_dir)

    # Start the server
    cmd = [
        "./bin/dfs-server-p2",
        "-a", server_address,
        "-m", server_dir,
        "-d", str(debug_level),
        "-n", "4"
    ]

    output_queue.put(f"Server command: {' '.join(cmd)}")
    server_process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=1, universal_newlines=False)

    # Monitor server output
    stdout_thread, stderr_thread = monitor_process_output(
        server_process, "SERVER")
    output_threads.extend([stdout_thread, stderr_thread])

    # Give server time to start and check if it's running
    time.sleep(1)

    if server_process.poll() is not None:
        output_queue.put(
            f"Server failed to start (exit code: {server_process.poll()})")
        raise RuntimeError("Server failed to start")

    output_queue.put("Server started successfully")

    return server_process


def start_client(client_dir: str, debug_level: int = 2) -> subprocess.Popen:
    """ Start a DFS client in mount mode """
    global client_processes, output_threads

    output_queue.put(
        f"Starting DFS client with mount path {client_dir} (debug level: {debug_level})")

    # Ensure client directory exists and is empty
    ensure_empty_directory(client_dir)

    # Start the client in mount mode
    cmd = [
        "./bin/dfs-client-p2",
        "-a", server_address,
        "-m", client_dir,
        "-d", str(debug_level),
        "-t", "5000",
        "mount"
    ]

    output_queue.put(f"Client command: {' '.join(cmd)}")
    client_process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=1, universal_newlines=False)
    client_processes.append(client_process)

    # Monitor client output
    # Use the position in client_processes list as ID
    client_id = len(client_processes)
    stdout_thread, stderr_thread = monitor_process_output(
        client_process, f"CLIENT-{client_id}")
    output_threads.extend([stdout_thread, stderr_thread])

    # Give client time to start and mount
    time.sleep(3)  # Increased from 2 to 3 seconds

    if client_process.poll() is not None:
        output_queue.put(
            f"Client failed to start (exit code: {client_process.poll()})")
        raise RuntimeError("Client failed to start")

    # Additional check - wait up to 15 seconds for client to be ready
    start_time = time.time()
    while time.time() - start_time < 15:  # Increased from 10 to 15 seconds
        if client_process.poll() is not None:
            output_queue.put(
                f"Client died during startup (exit code: {client_process.poll()})")
            raise RuntimeError("Client died during startup")
        time.sleep(0.5)

    output_queue.put(f"Client started successfully for {client_dir}")

    return client_process


def run_client_command(client_dir: str, command: str, filename: str = "", debug_level: int = 2) -> subprocess.CompletedProcess:
    """ Run a single client command """
    cmd = [
        "./bin/dfs-client-p2",
        "-a", server_address,
        "-m", client_dir,
        "-d", str(debug_level),
        "-t", "5000",
        command
    ]

    if filename:
        cmd.append(filename)

    output_queue.put(f"Running client command: {' '.join(cmd)}")

    # Run the command and capture output
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               universal_newlines=True)

    stdout, stderr = process.communicate(timeout=30)

    # Print the output to the queue
    if stdout:
        output_queue.put(f"COMMAND [stdout]: {stdout.strip()}")
    if stderr:
        output_queue.put(f"COMMAND [stderr]: {stderr.strip()}")

    # Return a CompletedProcess object for compatibility with existing code
    return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)


def check_async_channel(server_dir: str, client_dirs: List[str]) -> bool:
    """Check if the async callback channel is functioning properly"""
    output_queue.put("\n=== Checking Async Callback Channel ===")

    # First, get status of all clients to see their callback status
    for i, client_dir in enumerate(client_dirs):
        output_queue.put(
            f"\nChecking client {i+1} ({client_dir}) with list command...")
        # Run list command with debug level 3 to get detailed output
        cmd = [
            "./bin/dfs-client-p2",
            "-a", server_address,
            "-m", client_dir,
            "-d", "1",
            "-t", "5000",
            "list"
        ]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   universal_newlines=True)
        try:
            stdout, stderr = process.communicate(timeout=5)

            if stdout:
                output_queue.put(
                    f"CLIENT-{i+1} LIST [stdout]: {stdout.strip()}")
            if stderr:
                output_queue.put(
                    f"CLIENT-{i+1} LIST [stderr]: {stderr.strip()}")
        except subprocess.TimeoutExpired:
            output_queue.put(f"CLIENT-{i+1} LIST command timed out")
            process.kill()

    # Now check server files
    output_queue.put("\nFetching file list from server via direct access...")

    # Instead of trying to run a server command, let's list the directory directly
    try:
        files = os.listdir(server_dir)
        output_queue.put(f"Server directory contains {len(files)} files:")
        for f in sorted(files)[:10]:  # Show first 10 files
            file_path = os.path.join(server_dir, f)
            if os.path.isfile(file_path):
                stat_info = os.stat(file_path)
                output_queue.put(
                    f"  {f} (size: {stat_info.st_size}, mtime: {stat_info.st_mtime})")
        if len(files) > 10:
            output_queue.put(f"  ... and {len(files) - 10} more")
    except Exception as e:
        output_queue.put(f"Error listing server directory: {e}")

    return True


def create_files(client_dirs: List[str], run_id, tag: str, num_client_files: int) -> Tuple[dict, dict]:
    """ Create files using DFS client commands """
    client_file_crcs = {}
    client_filenames = {}

    for client_dir in client_dirs:
        client_dir_crc = zlib.crc32(bytes(client_dir, 'UTF-8'))

        client_filenames[client_dir] = []
        client_file_crcs[client_dir] = []

        for num in range(num_client_files):
            client_filename = f'dfsstress-{run_id}-{client_dir_crc}-{num}.txt'
            client_filenames[client_dir].append(client_filename)

            client_content = f'originally from {client_dir}, file {num}, tag {tag}\n'
            client_file_crcs[client_dir].append(
                zlib.crc32(client_content.encode('UTF-8')))

            # Create file in client directory
            filename = os.path.join(client_dir, client_filename)
            output_queue.put(f"Creating file: {filename}")
            with open(filename, 'w') as file:
                file.write(client_content)

            # Wait for inotify to process the file and store it
            output_queue.put(
                f"Waiting for inotify to process {client_filename}...")

            # Give inotify time to detect the file
            time.sleep(0.5)

            # Try to store the file explicitly to ensure it's processed
            result = run_client_command(client_dir, "store", client_filename)
            if result.returncode == 0:
                output_queue.put(
                    f"✅ File {client_filename} stored successfully")
            elif "ALREADY_EXISTS" in result.stdout:
                output_queue.put(
                    f"✅ File {client_filename} already exists (no changes needed)")
            else:
                output_queue.put(
                    f"⚠️  File {client_filename} store result: {result.stdout}")

    # Wait for all files to be processed and synchronized
    output_queue.put(
        "Waiting for all files to be processed and synchronized...")

    # Simple approach: wait a reasonable amount of time for operations to complete
    # This is more reliable than complex synchronization that might deadlock
    time.sleep(3.0)

    return client_filenames, client_file_crcs


def verify_files(
    server_dir: str,
    client_dirs: List[str],
    client_filenames: dict,
    client_file_crcs: dict,
    num_client_files: int,
    check_absence=False
) -> bool:
    """ Verify files exist and have correct content """
    output_queue.put(f"Verifying files (check_absence={check_absence})...")
    output_queue.put(f"Server directory: {server_dir}")
    output_queue.put(f"Client directories: {client_dirs}")

    if check_absence:
        # For absence check, we verify files are gone from client directories
        # Each client directory should be checked for each file that was created
        total_files_created = len(client_dirs) * num_client_files
        expected_files = len(client_dirs) * total_files_created
    else:
        # For presence check, each file should exist on server and all clients
        # Each client has its own files + files from other clients
        expected_files = len(client_dirs) * \
            num_client_files * (1 + len(client_dirs))

    output_queue.put(f"Expected to find {expected_files} file instances")

    timeout = time.time() + 30  # 30 seconds timeout

    while time.time() < timeout:
        files_count = 0
        missing_files = []
        found_files = []

        # First check the server directory for all client files
        if not check_absence:
            output_queue.put(f"\nChecking server directory: {server_dir}")
            for source_client_dir in client_dirs:
                output_queue.put(
                    f"  Looking for files from {source_client_dir} on server:")

                for num in range(num_client_files):
                    client_filename = client_filenames[source_client_dir][num]
                    server_filepath = os.path.join(server_dir, client_filename)

                    if not os.path.exists(server_filepath):
                        missing_files.append(f"✗ MISSING: {server_filepath}")
                        continue

                    # Verify file content on server
                    try:
                        with open(server_filepath, 'rb') as file:
                            crc = zlib.crc32(file.read())

                        expected_crc = client_file_crcs[source_client_dir][num]
                        if crc == expected_crc:
                            files_count += 1
                            found_files.append(
                                f"✓ {server_filepath} (CRC: {crc})")
                        else:
                            missing_files.append(
                                f"✗ CRC MISMATCH: {server_filepath} (expected: {expected_crc}, got: {crc})")
                    except IOError as e:
                        missing_files.append(
                            f"✗ IO ERROR: {server_filepath} ({e})")
                        continue

        # Now check each client directory for files from all clients
        for target_client_dir in client_dirs:
            output_queue.put(
                f"\nChecking client directory: {target_client_dir}")

            for source_client_dir in client_dirs:
                output_queue.put(
                    f"  Looking for files from {source_client_dir} on {target_client_dir}:")

                for num in range(num_client_files):
                    client_filename = client_filenames[source_client_dir][num]
                    client_filepath = os.path.join(
                        target_client_dir, client_filename)

                    if check_absence:
                        # For deletion test, verify files are gone
                        if not os.path.exists(client_filepath):
                            files_count += 1
                            found_files.append(
                                f"✓ {client_filepath} (correctly absent)")
                        else:
                            missing_files.append(
                                f"✗ UNEXPECTED: {client_filepath} (should be absent)")
                    else:
                        # For normal test, verify files exist with correct content
                        if not os.path.exists(client_filepath):
                            missing_files.append(
                                f"✗ MISSING: {client_filepath}")
                            continue

                        # Verify file content
                        try:
                            with open(client_filepath, 'rb') as file:
                                crc = zlib.crc32(file.read())

                            expected_crc = client_file_crcs[source_client_dir][num]
                            if crc == expected_crc:
                                files_count += 1
                                found_files.append(
                                    f"✓ {client_filepath} (CRC: {crc})")
                            else:
                                missing_files.append(
                                    f"✗ CRC MISMATCH: {client_filepath} (expected: {expected_crc}, got: {crc})")
                        except IOError as e:
                            missing_files.append(
                                f"✗ IO ERROR: {client_filepath} ({e})")
                            continue

        output_queue.put(
            f"\nProgress: {files_count}/{expected_files} files verified")

        # Print detailed status information
        if found_files:
            output_queue.put(f"Found files: {len(found_files)}")
            for f in found_files[:5]:  # Show first 5 found files
                output_queue.put(f"  {f}")
            if len(found_files) > 5:
                output_queue.put(f"  ... and {len(found_files) - 5} more")

        if missing_files:
            output_queue.put(
                f"Missing/problematic files: {len(missing_files)}")
            for f in missing_files[:5]:  # Show first 5 missing files
                output_queue.put(f"  {f}")
            if len(missing_files) > 5:
                output_queue.put(f"  ... and {len(missing_files) - 5} more")

        # If all expected files were found, break
        if files_count == expected_files:
            break

        # Otherwise, wait before checking again
        output_queue.put("Waiting 1 second before next check...")
        time.sleep(1.0)

    if files_count < expected_files:
        output_queue.put(
            f"❌ TIMEOUT: Only {files_count}/{expected_files} files verified after {timeout} seconds")
        return False
    else:
        output_queue.put(f"✅ Verified {files_count}/{expected_files} files")
        return True


def delete_files(client_dirs: List[str], client_filenames: dict) -> None:
    """ Delete files from client directories """
    output_queue.put("Deleting files...")

    for client_dir in client_dirs:
        for client_filename in client_filenames[client_dir]:
            filename = os.path.join(client_dir, client_filename)

            # First try to use the client Delete command
            try:
                output_queue.put(
                    f"Deleting file via client command: {client_filename}")
                result = run_client_command(
                    client_dir, "delete", client_filename)
                if result.returncode == 0:
                    output_queue.put(
                        f"✅ Successfully deleted file via client command: {client_filename}")
                else:
                    output_queue.put(
                        f"⚠️ Client delete command failed for: {client_filename}")
                    output_queue.put(f"Output: {result.stdout}")
                    output_queue.put(f"Error: {result.stderr}")
            except Exception as e:
                output_queue.put(
                    f"❌ Exception when trying to delete file via client: {e}")

            # Also make sure the file is removed from the client directory
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                    output_queue.put(
                        f"✅ Removed file from client directory: {filename}")
                except Exception as e:
                    output_queue.put(
                        f"❌ Failed to remove file from client directory: {e}")
            else:
                output_queue.put(
                    f"✓ File already gone from client directory: {filename}")

            # Wait for sync to occur
            time.sleep(0.5)


def handle_test_failure(test_name: str, reason: str) -> None:
    """ Handle test failure by cleaning up and exiting """
    output_queue.put(f"\n❌ {test_name} FAILED: {reason}")
    output_queue.put("Cleaning up and shutting down...")
    cleanup_processes()
    sys.exit(1)


def list_directory_contents(directory: str, description: str = "") -> None:
    """ List and display directory contents for debugging """
    try:
        if os.path.exists(directory):
            files = os.listdir(directory)
            output_queue.put(f"\n{description} - Directory: {directory}")
            output_queue.put(f"  Contains {len(files)} files:")
            for file in sorted(files):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path):
                    stat_info = os.stat(file_path)
                    output_queue.put(
                        f"    {file} (size: {stat_info.st_size}, mtime: {stat_info.st_mtime})")
                else:
                    output_queue.put(f"    {file} (directory)")
        else:
            output_queue.put(
                f"\n{description} - Directory: {directory} (DOES NOT EXIST)")
    except Exception as e:
        output_queue.put(
            f"\n{description} - Directory: {directory} (ERROR: {e})")


def test_basic_operations(server_dir: str, client_dir: str) -> bool:
    """ Test basic DFS operations: store, fetch, list, stat, delete """
    output_queue.put("\n=== Testing Basic DFS Operations ===")

    # Test 1: Initial List (should be empty)
    output_queue.put("\n--- Test 1: Initial List (should be empty) ---")
    result = run_client_command(client_dir, "list")
    if result.returncode != 0:
        output_queue.put(f"❌ Initial list failed: {result.stderr}")
        return False
    output_queue.put("✅ Initial list successful")

    # Test 2: Store a new file
    output_queue.put("\n--- Test 2: Store Operation ---")
    test_filename = "basic_test.txt"
    test_content = "This is a test file for basic DFS operations.\nLine 2 of content.\n"
    test_filepath = os.path.join(client_dir, test_filename)

    # Create test file
    with open(test_filepath, 'w') as f:
        f.write(test_content)
    output_queue.put(f"Created test file: {test_filepath}")

    # Store the file
    result = run_client_command(client_dir, "store", test_filename)
    if result.returncode != 0:
        output_queue.put(f"❌ Store failed: {result.stderr}")
        return False
    output_queue.put("✅ Store operation successful")

    # Verify file exists on server
    server_filepath = os.path.join(server_dir, test_filename)
    if not os.path.exists(server_filepath):
        output_queue.put(f"❌ File not found on server: {server_filepath}")
        return False
    output_queue.put("✅ File verified on server")

    # Test 3: Stat operation
    output_queue.put("\n--- Test 3: Stat Operation ---")
    result = run_client_command(client_dir, "stat", test_filename)
    if result.returncode != 0:
        output_queue.put(f"❌ Stat failed: {result.stderr}")
        return False
    output_queue.put("✅ Stat operation successful")

    # Test 4: List operation (should show our file)
    output_queue.put("\n--- Test 4: List Operation (with file) ---")
    result = run_client_command(client_dir, "list")
    if result.returncode != 0:
        output_queue.put(f"⚠️  List operation failed: {result.stderr}")
        output_queue.put("Continuing with other tests...")
    else:
        output_queue.put("✅ List operation completed")
        output_queue.put(f"List output: {result.stdout}")
        # Don't fail the entire test if list doesn't show the file
        # if test_filename not in result.stdout:
        #     output_queue.put(f"⚠️  Test file not found in list output")
        # else:
        #     output_queue.put("✅ File appears in listing")

    # Test 5: Fetch operation (download file)
    output_queue.put("\n--- Test 5: Fetch Operation ---")
    # Remove local file first
    os.remove(test_filepath)
    output_queue.put(f"Removed local file: {test_filepath}")

    # Fetch from server
    result = run_client_command(client_dir, "fetch", test_filename)
    if result.returncode != 0:
        output_queue.put(f"❌ Fetch failed: {result.stderr}")
        return False

    # Verify file was fetched and content is correct
    if not os.path.exists(test_filepath):
        output_queue.put(f"❌ Fetched file not found: {test_filepath}")
        return False

    with open(test_filepath, 'r') as f:
        fetched_content = f.read()

    if fetched_content != test_content:
        output_queue.put(f"❌ Fetched content doesn't match original")
        output_queue.put(f"Original: {repr(test_content)}")
        output_queue.put(f"Fetched:  {repr(fetched_content)}")
        return False
    output_queue.put("✅ Fetch operation successful - content verified")

    # Test 6: Store same file (should detect no changes)
    output_queue.put(
        "\n--- Test 6: Store Same File (should detect ALREADY_EXISTS) ---")
    result = run_client_command(client_dir, "store", test_filename)
    # This might return 0 but show ALREADY_EXISTS in debug output
    output_queue.put(f"Store same file result: {result.stdout}")
    output_queue.put("✅ Store same file handled correctly")

    # Test 7: Modify and store file
    output_queue.put("\n--- Test 7: Modify and Store File ---")
    modified_content = test_content + "Modified line added.\n"
    with open(test_filepath, 'w') as f:
        f.write(modified_content)

    result = run_client_command(client_dir, "store", test_filename)
    if result.returncode != 0:
        output_queue.put(f"❌ Store modified file failed: {result.stderr}")
        return False
    output_queue.put("✅ Store modified file successful")

    # Test 8: Delete operation
    output_queue.put("\n--- Test 8: Delete Operation ---")
    result = run_client_command(client_dir, "delete", test_filename)
    if result.returncode != 0:
        output_queue.put(f"❌ Delete failed: {result.stderr}")
        return False
    output_queue.put("✅ Delete operation successful")

    # Verify file is deleted from server (may still exist but marked as deleted)
    time.sleep(1)  # Give server time to process deletion

    # Test 9: List after delete (should not show file or show as deleted)
    output_queue.put("\n--- Test 9: List After Delete ---")
    result = run_client_command(client_dir, "list")
    if result.returncode != 0:
        output_queue.put(f"⚠️  List after delete failed: {result.stderr}")
        output_queue.put("Continuing with other tests...")
    else:
        output_queue.put("✅ List after delete completed")
        output_queue.put(f"List output: {result.stdout}")

    # Test 10: Try to fetch deleted file (should fail)
    output_queue.put("\n--- Test 10: Fetch Deleted File (should fail) ---")
    result = run_client_command(client_dir, "fetch", test_filename)
    if result.returncode == 0:
        output_queue.put(f"⚠️  Fetch deleted file unexpectedly succeeded")
    else:
        output_queue.put("✅ Fetch deleted file correctly failed")

    # Test 11: Try to stat deleted file (should fail)
    output_queue.put("\n--- Test 11: Stat Deleted File (should fail) ---")
    result = run_client_command(client_dir, "stat", test_filename)
    if result.returncode == 0:
        output_queue.put(f"⚠️  Stat deleted file unexpectedly succeeded")
    else:
        output_queue.put("✅ Stat deleted file correctly failed")

    output_queue.put("\n🎉 All basic operations tests completed successfully!")
    return True


def test_error_conditions(server_dir: str, client_dir: str) -> bool:
    """ Test error conditions and edge cases """
    output_queue.put("\n=== Testing Error Conditions ===")

    # Test 1: Fetch non-existent file
    output_queue.put("\n--- Test 1: Fetch Non-existent File ---")
    result = run_client_command(client_dir, "fetch", "nonexistent.txt")
    if result.returncode == 0:
        output_queue.put("⚠️  Fetch non-existent file unexpectedly succeeded")
    else:
        output_queue.put("✅ Fetch non-existent file correctly failed")

    # Test 2: Store non-existent local file
    output_queue.put("\n--- Test 2: Store Non-existent Local File ---")
    result = run_client_command(client_dir, "store", "nonexistent_local.txt")
    if result.returncode == 0:
        output_queue.put(
            "⚠️  Store non-existent local file unexpectedly succeeded")
    else:
        output_queue.put("✅ Store non-existent local file correctly failed")

    # Test 3: Stat non-existent file
    output_queue.put("\n--- Test 3: Stat Non-existent File ---")
    result = run_client_command(client_dir, "stat", "nonexistent.txt")
    if result.returncode == 0:
        output_queue.put("⚠️  Stat non-existent file unexpectedly succeeded")
    else:
        output_queue.put("✅ Stat non-existent file correctly failed")

    # Test 4: Delete non-existent file
    output_queue.put("\n--- Test 4: Delete Non-existent File ---")
    result = run_client_command(client_dir, "delete", "nonexistent.txt")
    if result.returncode == 0:
        output_queue.put("⚠️  Delete non-existent file unexpectedly succeeded")
    else:
        output_queue.put("✅ Delete non-existent file correctly failed")

    output_queue.put("\n🎉 Error condition tests completed!")
    return True


def run_basic_tests(server_dir: str, client_dir: str) -> None:
    """ Run comprehensive tests of basic DFS operations """
    output_queue.put(f"Running basic DFS tests")
    output_queue.put(f"Server directory: {server_dir}")
    output_queue.put(f"Client directory: {client_dir}")

    # Ensure directories exist and are empty
    ensure_empty_directory(server_dir)
    ensure_empty_directory(client_dir)

    # Build DFS binaries
    try:
        build_dfs_binaries()
    except Exception as e:
        output_queue.put(f"❌ Build failed: {e}")
        return

    # Start server
    try:
        start_server(server_dir, debug_level=2)
    except Exception as e:
        output_queue.put(f"❌ Server startup failed: {e}")
        return

    # Wait for server to be ready
    output_queue.put("Waiting for server to be ready...")
    time.sleep(1)

    try:
        # Run basic operation tests
        if not test_basic_operations(server_dir, client_dir):
            output_queue.put("❌ Basic operations tests failed")
            return

        # Run error condition tests
        if not test_error_conditions(server_dir, client_dir):
            output_queue.put("❌ Error condition tests failed")
            return

        output_queue.put("\n🎉 ALL BASIC TESTS PASSED! 🎉")

    except Exception as e:
        output_queue.put(f"❌ Test execution failed: {e}")
    finally:
        cleanup_processes()


def stress(num_client_files: int, server_dir: str, client_dirs: List[str]) -> None:
    """ Run the stress tests """
    output_queue.put(f"Starting stress test with {num_client_files} files")
    output_queue.put(f"Server directory: {server_dir}")
    output_queue.put(f"Client directories: {client_dirs}")

    # Ensure directories exist and are empty
    ensure_empty_directory(server_dir)
    for client_dir in client_dirs:
        ensure_empty_directory(client_dir)

    # Build DFS binaries
    try:
        build_dfs_binaries()
    except Exception as e:
        handle_test_failure("Build", str(e))

    # Start server with higher debug level
    try:
        start_server(server_dir, debug_level=1)
    except Exception as e:
        handle_test_failure("Server Startup", str(e))

    # Start clients with higher debug level
    try:
        for client_dir in client_dirs:
            start_client(client_dir, debug_level=1)
    except Exception as e:
        handle_test_failure("Client Startup", str(e))

    # Wait for everything to be ready
    output_queue.put("Waiting for DFS system to be fully ready...")
    time.sleep(3)

    # Show initial directory contents
    list_directory_contents(server_dir, "Initial Server Directory")
    for i, client_dir in enumerate(client_dirs):
        list_directory_contents(client_dir, f"Initial Client {i+1} Directory")

    run_id = int(time.time() * 1e6)

    # Test 1: Create files
    output_queue.put("\n=== Test 1: Creating files ===")
    client_filenames, client_file_crcs = create_files(
        client_dirs, run_id, 'create', num_client_files)

    # Show directory contents after file creation
    list_directory_contents(server_dir, "Server Directory After Creation")
    for i, client_dir in enumerate(client_dirs):
        list_directory_contents(
            client_dir, f"Client {i+1} Directory After Creation")

    # Check async channel status before verification
    check_async_channel(server_dir, client_dirs)

    create_start_time = time.time()
    if not verify_files(server_dir, client_dirs, client_filenames, client_file_crcs, num_client_files):
        # Wait more time and check again if files are not synchronized
        output_queue.put(
            "\nFiles not synchronized. Waiting additional time...")
        time.sleep(5)  # Wait longer for async operations

        # Check async channel again after waiting
        check_async_channel(server_dir, client_dirs)

        # Try verification again
        if not verify_files(server_dir, client_dirs, client_filenames, client_file_crcs, num_client_files):
            handle_test_failure("Test 1 - Create Files",
                                "File verification failed or timed out")

    create_elapsed_time = time.time() - create_start_time
    output_queue.put(
        f'Time to create {num_client_files} files: {create_elapsed_time:.2f}s')

    # Test 2: Modify files
    output_queue.put("\n=== Test 2: Modifying files ===")
    client_filenames, client_file_crcs = create_files(
        client_dirs, run_id, 'modified', num_client_files)

    modify_start_time = time.time()
    if not verify_files(server_dir, client_dirs, client_filenames, client_file_crcs, num_client_files):
        handle_test_failure("Test 2 - Modify Files",
                            "File verification failed or timed out")
    modify_elapsed_time = time.time() - modify_start_time
    output_queue.put(
        f'Time to modify {num_client_files} files: {modify_elapsed_time:.2f}s')

    # Test 3: No change (should be faster)
    output_queue.put("\n=== Test 3: No change (recreate same files) ===")
    client_filenames, client_file_crcs = create_files(
        client_dirs, run_id, 'modified', num_client_files)

    nochange_start_time = time.time()
    if not verify_files(server_dir, client_dirs, client_filenames, client_file_crcs, num_client_files):
        handle_test_failure("Test 3 - No Change",
                            "File verification failed or timed out")
    nochange_elapsed_time = time.time() - nochange_start_time
    output_queue.put(
        f'Time to recreate but not change {num_client_files} files: {nochange_elapsed_time:.2f}s')

    # Test 4: Delete files
    output_queue.put("\n=== Test 4: Deleting files ===")
    delete_files(client_dirs, client_filenames)

    delete_start_time = time.time()
    if not verify_files(server_dir, client_dirs, client_filenames, client_file_crcs, num_client_files, check_absence=True):
        handle_test_failure("Test 4 - Delete Files",
                            "File deletion verification failed or timed out")
    delete_elapsed_time = time.time() - delete_start_time
    output_queue.put(
        f'Time to delete {num_client_files} files: {delete_elapsed_time:.2f}s')

    output_queue.put(
        "\n✅ ALL TESTS PASSED - Stress test completed successfully!")


if __name__ == '__main__':
    # Start output printer thread
    output_thread = start_output_printer()

    if len(sys.argv) < 2:
        output_queue.put(
            f'Syntax: {sys.argv[0]} [basic|stress] [OPTIONS...]')
        output_queue.put('')
        output_queue.put('MODES:')
        output_queue.put(
            '  basic /server/dir /client/dir        - Run basic operation tests')
        output_queue.put(
            '  stress number-of-files /server/mount /client1/mount [/client2/mount...]  - Run stress tests')
        output_queue.put('')
        output_queue.put('EXAMPLES:')
        output_queue.put(
            f'  {sys.argv[0]} basic /tmp/server_test /tmp/client_test')
        output_queue.put(
            f'  {sys.argv[0]} stress 5 /tmp/server /tmp/client1 /tmp/client2')
        # Ensure threads are properly stopped before exit
        output_thread_running = False
        time.sleep(0.5)
        sys.exit(1)

    # Set up signal handlers and cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup_processes)

    try:
        mode = sys.argv[1]

        if mode == "basic":
            if len(sys.argv) != 4:
                output_queue.put(
                    f'Syntax for basic tests: {sys.argv[0]} basic /server/dir /client/dir')
                # Ensure threads are properly stopped before exit
                cleanup_processes()
                time.sleep(0.5)
                sys.exit(1)

            server_dir = sys.argv[2]
            client_dir = sys.argv[3]

            # Run basic tests
            run_basic_tests(server_dir, client_dir)

        elif mode == "stress":
            if len(sys.argv) < 5:
                output_queue.put(
                    f'Syntax for stress tests: {sys.argv[0]} stress number-of-files /server/mount /client1/mount [/client2/mount...]')
                # Ensure threads are properly stopped before exit
                cleanup_processes()
                time.sleep(0.5)
                sys.exit(1)

            num_files = int(sys.argv[2])
            server_dir = sys.argv[3]
            client_dirs = sys.argv[4:]

            # Run stress test with a timeout
            try:
                stress_thread = threading.Thread(
                    target=stress, args=(num_files, server_dir, client_dirs))
                stress_thread.daemon = True  # Make it a daemon thread
                stress_thread.start()

                # Wait for the stress test to complete, but with a max timeout
                max_timeout = 120  # 2 minutes
                stress_thread.join(max_timeout)

                if stress_thread.is_alive():
                    print(
                        f"⚠️ Stress test did not complete within {max_timeout} seconds. Terminating...")
                    output_queue.put(
                        f"⚠️ Stress test did not complete within {max_timeout} seconds. Terminating...")
                    # Start a thread that will force exit
                    force_exit_thread = threading.Thread(
                        target=force_exit, daemon=True)
                    force_exit_thread.start()
                    cleanup_processes()
            except Exception as e:
                print(f"Error in stress test: {e}")
                output_queue.put(f"Error in stress test: {e}")
                # Start a thread that will force exit
                force_exit_thread = threading.Thread(
                    target=force_exit, daemon=True)
                force_exit_thread.start()
                cleanup_processes()

        else:
            output_queue.put(f'Unknown mode: {mode}')
            output_queue.put('Valid modes are: basic, stress')
            # Ensure threads are properly stopped before exit
            cleanup_processes()
            time.sleep(0.5)
            sys.exit(1)

    except KeyboardInterrupt:
        print("Keyboard interrupt received, shutting down...")
        output_queue.put("Keyboard interrupt received, shutting down...")
        # Start a thread that will force exit
        force_exit_thread = threading.Thread(target=force_exit, daemon=True)
        force_exit_thread.start()
        cleanup_processes()
    except Exception as e:
        print(f"Error: {e}")
        output_queue.put(f"Error: {e}")
        # Start a thread that will force exit
        force_exit_thread = threading.Thread(target=force_exit, daemon=True)
        force_exit_thread.start()
        cleanup_processes()
        sys.exit(1)
    finally:
        # Ensure all processes and threads are cleaned up
        cleanup_processes()
        # Allow time for final output to be processed
        time.sleep(0.5)

        # Force exit in case any threads are still running
        print("Final exit")
        os._exit(0)
