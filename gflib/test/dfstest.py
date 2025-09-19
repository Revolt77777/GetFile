#!/usr/bin/python3

""" DFS Part1 Test Script """

import os
import sys
import time
import zlib
import random
import subprocess
from typing import Dict


class DFSTest:
    def __init__(self):
        self.server_process = None
        self.server_dir = "mnt/server"
        self.client_dir = "mnt/client"
        self.server_bin = "bin/dfs-server-p1"
        self.client_bin = "bin/dfs-client-p1"
        self.server_address = "127.0.0.1:54080"
        self.test_files = {}
        self.run_id = int(time.time() * 1e6)

    def setup(self):
        """Setup test environment"""
        print("Setting up DFS test environment...")

        # Ensure mount directories exist
        os.makedirs(self.server_dir, exist_ok=True)
        os.makedirs(self.client_dir, exist_ok=True)

        # Clean up any existing test files
        self.cleanup_test_files()

        # Get number of CPU cores for parallel build
        try:
            num_cores = str(os.cpu_count() or 4)
        except:
            num_cores = "4"

        print("Running 'make clean_all protos part1'...")

        result = subprocess.run(
            ["make", "clean_all"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Make clean_all failed: {result.stderr}")
            return False

        result = subprocess.run(
            ["make", "protos"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Make protos failed: {result.stderr}")
            return False

        result = subprocess.run(
            ["make", f"-j{num_cores}", "part1"], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Part1 build failed: {result.stderr}")
            return False
        print("Part1 build successful!")

        return True

    def cleanup_test_files(self):
        """Clean up test files from previous runs"""
        for dir_path in [self.server_dir, self.client_dir]:
            if os.path.exists(dir_path):
                for file in os.listdir(dir_path):
                    if file.startswith('dfstest-'):
                        try:
                            os.remove(os.path.join(dir_path, file))
                        except:
                            pass

    def start_server(self):
        """Start the DFS server"""
        print(f"Starting DFS server on {self.server_address}...")

        # Kill any existing server process
        subprocess.run(["pkill", "-f", "dfs-server-p1"], capture_output=True)
        time.sleep(1)

        # Start the server
        self.server_process = subprocess.Popen([
            self.server_bin,
            "-a", self.server_address,
            "-m", self.server_dir,
            "-d", "1"  # Enable debug output
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Give server time to start
        time.sleep(2)

        if self.server_process.poll() is not None:
            stdout, stderr = self.server_process.communicate()
            print(f"Server failed to start: {stderr}")
            return False

        print("Server started successfully")
        return True

    def stop_server(self):
        """Stop the DFS server"""
        if self.server_process:
            print("Stopping DFS server...")
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
                self.server_process.wait()
            self.server_process = None

    def create_test_files(self, num_files: int) -> Dict[str, int]:
        """Create test files in server directory"""
        print(f"Creating {num_files} test files in {self.server_dir}...")

        file_crcs = {}

        for i in range(num_files):
            filename = f"dfstest-{self.run_id}-{i:03d}.bin"
            filepath = os.path.join(self.server_dir, filename)

            file_size = random.randint(0, 5 * 1024 * 1024)

            # Generate random binary content
            content = os.urandom(file_size)

            with open(filepath, 'wb') as f:
                f.write(content)

            # Calculate CRC for verification
            file_crcs[filename] = zlib.crc32(content)

            print(f"Created {filename}: {file_size:,} bytes")

        self.test_files = file_crcs
        print(f"Created {len(file_crcs)} test files with random sizes")
        return file_crcs

    def run_client_command(self, command: str, filename: str = "") -> tuple:
        """Run a DFS client command"""
        cmd = [
            self.client_bin,
            "-a", self.server_address,
            "-m", self.client_dir,
            "-d", "1",
            command
        ]

        if filename:
            cmd.append(filename)

        print(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr

    def verify_file_sync(self, filename: str, expected_crc: int) -> bool:
        """Verify that a file has synced correctly to client"""
        client_path = os.path.join(self.client_dir, filename)

        # Wait for file to appear (up to 10 seconds)
        for _ in range(20):
            if os.path.exists(client_path):
                break
            time.sleep(0.5)
        else:
            print(f"File {filename} did not sync to client")
            return False

        # Verify content matches
        try:
            with open(client_path, 'rb') as f:
                content = f.read()
                actual_crc = zlib.crc32(content)

            if actual_crc == expected_crc:
                print(f"PASS File {filename} synced correctly")
                return True
            else:
                print(
                    f"FAIL File {filename} CRC mismatch: expected {expected_crc}, got {actual_crc}")
                return False

        except Exception as e:
            print(f"FAIL Error verifying file {filename}: {e}")
            return False

    def test_store_operation(self) -> bool:
        """Test store operation"""
        print("\n--- Testing STORE operation ---")

        # Create a test file in client directory
        test_filename = f"dfstest-store-{self.run_id}.bin"
        # Generate random binary content for store test (medium size: 50KB-500KB)
        test_size = random.randint(50 * 1024, 500 * 1024)
        test_content = os.urandom(test_size)
        client_path = os.path.join(self.client_dir, test_filename)

        with open(client_path, 'wb') as f:
            f.write(test_content)

        expected_crc = zlib.crc32(test_content)
        print(f"Created store test file: {test_size:,} bytes")

        # Store the file
        returncode, stdout, stderr = self.run_client_command(
            "store", test_filename)

        # Always display stderr, regardless of return code
        if stderr.strip():
            print(f"Store stderr output:\n{stderr}")
        else:
            print("Store stderr: (empty)")

        # Always display stdout, regardless of return code
        if stdout.strip():
            print(f"Store stdout:\n{stdout}")
        else:
            print("Store stdout: (empty)")

        if returncode != 0:
            print(f"FAIL Store command failed with return code {returncode}")
            return False

        # Check if the operation actually succeeded by checking debug output
        if "store OK" not in stderr:
            print(
                f"FAIL Store command did not complete successfully - expected 'store OK' in stderr")
            return False

        # Verify file appears on server
        server_path = os.path.join(self.server_dir, test_filename)
        time.sleep(1)  # Give time for operation to complete

        if not os.path.exists(server_path):
            print(f"FAIL File {test_filename} not found on server")
            return False

        # Verify content
        with open(server_path, 'rb') as f:
            server_content = f.read()
            server_crc = zlib.crc32(server_content)

        if server_crc == expected_crc:
            print(f"PASS Store operation successful")
            return True
        else:
            print(f"FAIL Store operation failed - content mismatch")
            return False

    def test_fetch_operation(self) -> bool:
        """Test fetch operation"""
        print("\n--- Testing FETCH operation ---")

        if not self.test_files:
            print("FAIL No test files available for fetch test")
            return False

        # Pick first test file
        filename = list(self.test_files.keys())[0]
        expected_crc = self.test_files[filename]

        # Remove file from client if it exists
        client_path = os.path.join(self.client_dir, filename)
        if os.path.exists(client_path):
            os.remove(client_path)

        # Fetch the file
        returncode, stdout, stderr = self.run_client_command("fetch", filename)

        print(f"Fetch stdout:\n{stdout}")
        print(f"Fetch stderr:\n{stderr}")

        if returncode != 0:
            print(f"FAIL Fetch command failed with return code {returncode}")
            return False

        # Verify file appears on client
        return self.verify_file_sync(filename, expected_crc)

    def test_list_operation(self) -> bool:
        """Test list operation"""
        print("\n--- Testing LIST operation ---")

        returncode, stdout, stderr = self.run_client_command("list")

        print(f"List stdout:\n{stdout}")
        print(f"List stderr:\n{stderr}")

        if returncode != 0:
            print(f"FAIL List command failed with return code {returncode}")
            return False

        # Check if our test files appear in the listing
        found_files = 0
        for filename in self.test_files.keys():
            if filename in stdout or filename in stderr:
                found_files += 1

        if found_files > 0:
            print(
                f"PASS List operation successful - found {found_files} test files")
            return True
        else:
            print(f"FAIL List operation failed - no test files found in output")
            return False

    def test_delete_operation(self) -> bool:
        """Test delete operation"""
        print("\n--- Testing DELETE operation ---")

        if not self.test_files:
            print("FAIL No test files available for delete test")
            return False

        # Pick last test file
        filename = list(self.test_files.keys())[-1]

        # Delete the file
        returncode, stdout, stderr = self.run_client_command(
            "delete", filename)

        print(f"Delete stdout:\n{stdout}")
        print(f"Delete stderr:\n{stderr}")

        if returncode != 0:
            print(f"FAIL Delete command failed with return code {returncode}")
            return False

        # Verify file is removed from server
        server_path = os.path.join(self.server_dir, filename)
        time.sleep(1)  # Give time for operation to complete

        if os.path.exists(server_path):
            print(f"FAIL File {filename} still exists on server after delete")
            return False
        else:
            print(f"PASS Delete operation successful")
            return True

    def test_stat_operation(self) -> bool:
        """Test stat operation"""
        print("\n--- Testing STAT operation ---")

        if not self.test_files:
            print("FAIL No test files available for stat test")
            return False

        # Pick first test file
        filename = list(self.test_files.keys())[0]

        # Stat the file
        returncode, stdout, stderr = self.run_client_command("stat", filename)

        print(f"Stat stdout:\n{stdout}")
        print(f"Stat stderr:\n{stderr}")

        if returncode != 0:
            print(f"FAIL Stat command failed with return code {returncode}")
            return False

        # Check if output contains expected information
        if filename in stdout or filename in stderr:
            print(f"PASS Stat operation successful")
            return True
        else:
            print(f"FAIL Stat operation failed - filename not found in output")
            return False

    def test_fetch_not_found(self) -> bool:
        """Test fetch operation on nonexistent file"""
        print("\n--- Testing FETCH NOT_FOUND ---")

        nonexistent_file = f"nonexistent-fetch-{self.run_id}.txt"

        # Fetch the nonexistent file
        returncode, stdout, stderr = self.run_client_command(
            "fetch", nonexistent_file)

        print(f"Fetch NOT_FOUND stdout:\n{stdout}")
        print(f"Fetch NOT_FOUND stderr:\n{stderr}")

        if returncode != 0:
            print(
                f"FAIL Fetch NOT_FOUND command failed with return code {returncode}")
            return False

        # Check if output contains NOT_FOUND
        if "NOT_FOUND" in stderr:
            print(f"PASS Fetch NOT_FOUND operation successful")
            return True
        else:
            print(
                f"FAIL Fetch NOT_FOUND operation failed - NOT_FOUND not found in output")
            return False

    def test_delete_not_found(self) -> bool:
        """Test delete operation on nonexistent file"""
        print("\n--- Testing DELETE NOT_FOUND ---")

        nonexistent_file = f"nonexistent-delete-{self.run_id}.txt"

        # Delete the nonexistent file
        returncode, stdout, stderr = self.run_client_command(
            "delete", nonexistent_file)

        print(f"Delete NOT_FOUND stdout:\n{stdout}")
        print(f"Delete NOT_FOUND stderr:\n{stderr}")

        if returncode != 0:
            print(
                f"FAIL Delete NOT_FOUND command failed with return code {returncode}")
            return False

        # Check if output contains NOT_FOUND
        if "NOT_FOUND" in stderr:
            print(f"PASS Delete NOT_FOUND operation successful")
            return True
        else:
            print(
                f"FAIL Delete NOT_FOUND operation failed - NOT_FOUND not found in output")
            return False

    def test_stat_not_found(self) -> bool:
        """Test stat operation on nonexistent file"""
        print("\n--- Testing STAT NOT_FOUND ---")

        nonexistent_file = f"nonexistent-stat-{self.run_id}.txt"

        # Stat the nonexistent file
        returncode, stdout, stderr = self.run_client_command(
            "stat", nonexistent_file)

        print(f"Stat NOT_FOUND stdout:\n{stdout}")
        print(f"Stat NOT_FOUND stderr:\n{stderr}")

        if returncode != 0:
            print(
                f"FAIL Stat NOT_FOUND command failed with return code {returncode}")
            return False

        # Check if output contains NOT_FOUND
        if "NOT_FOUND" in stderr:
            print(f"PASS Stat NOT_FOUND operation successful")
            return True
        else:
            print(f"FAIL Stat NOT_FOUND operation failed - NOT_FOUND not found in output")
            return False

    def test_store_not_found(self) -> bool:
        """Test store operation on nonexistent local file"""
        print("\n--- Testing STORE NOT_FOUND ---")

        nonexistent_file = f"nonexistent-store-{self.run_id}.txt"

        # Make sure the file doesn't exist in client directory
        client_path = os.path.join(self.client_dir, nonexistent_file)
        if os.path.exists(client_path):
            os.remove(client_path)

        # Store the nonexistent file
        returncode, stdout, stderr = self.run_client_command(
            "store", nonexistent_file)

        print(f"Store NOT_FOUND stdout:\n{stdout}")
        print(f"Store NOT_FOUND stderr:\n{stderr}")

        if returncode != 0:
            print(
                f"FAIL Store NOT_FOUND command failed with return code {returncode}")
            return False

        # Check if output contains NOT_FOUND
        if "NOT_FOUND" in stderr:
            print(f"PASS Store NOT_FOUND operation successful")
            return True
        else:
            print(
                f"FAIL Store NOT_FOUND operation failed - NOT_FOUND not found in output")
            return False

    def run_comprehensive_test(self, num_files: int = 5) -> bool:
        """Run comprehensive DFS test"""
        print(f"\n{'='*60}")
        print(f"Starting DFS Part1 Comprehensive Test")
        print(f"Test files: {num_files}")
        print(f"Server dir: {self.server_dir}")
        print(f"Client dir: {self.client_dir}")
        print(f"{'='*60}")

        # Setup
        if not self.setup():
            print("FAIL Setup failed")
            return False

        # Start server
        if not self.start_server():
            print("FAIL Server startup failed")
            return False

        try:
            # Create test files
            self.create_test_files(num_files)

            # Test all operations
            tests = [
                ("LIST", self.test_list_operation),
                ("FETCH", self.test_fetch_operation),
                ("STORE", self.test_store_operation),
                ("STAT", self.test_stat_operation),
                ("DELETE", self.test_delete_operation),
                ("FETCH_NOT_FOUND", self.test_fetch_not_found),
                ("DELETE_NOT_FOUND", self.test_delete_not_found),
                ("STAT_NOT_FOUND", self.test_stat_not_found),
                ("STORE_NOT_FOUND", self.test_store_not_found),
            ]

            passed = 0
            total = len(tests)

            for test_name, test_func in tests:
                print(f"\n{'='*40}")
                try:
                    if test_func():
                        passed += 1
                        print(f"PASS {test_name} test PASSED")
                    else:
                        print(f"FAIL {test_name} test FAILED")
                except Exception as e:
                    print(f"FAIL {test_name} test ERROR: {e}")

            print(f"\n{'='*60}")
            print(f"Test Results: {passed}/{total} tests passed")
            print(f"{'='*60}")

            return passed == total

        finally:
            # Cleanup
            self.stop_server()

    def cleanup(self):
        """Final cleanup"""
        self.stop_server()
        self.cleanup_test_files()


def main():
    if len(sys.argv) > 1:
        try:
            num_files = int(sys.argv[1])
        except ValueError:
            print("Usage: python3 dfstest.py [num_files]")
            sys.exit(1)
    else:
        num_files = 5

    test = DFSTest()

    try:
        success = test.run_comprehensive_test(num_files)
        if success:
            print("\nSUCCESS: All tests passed! DFS implementation is working correctly.")
            sys.exit(0)
        else:
            print("\nFAILED: Some tests failed. Please check the implementation.")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        sys.exit(1)
    finally:
        test.cleanup()


if __name__ == "__main__":
    main()
