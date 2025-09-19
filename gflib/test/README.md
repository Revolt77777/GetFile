# 6200-tools
GIOS 6200 tools

Original author: Miguel Paraz <mparaz@gatech.edu> from Graduate Introduction to Operating Systems 6200, Spring 2022.

These tools are freely available to use and reuse for any purpose, especially for but not limited to future classes and students.

# Python test clients for Getfile client wire protocol:

## Installing python
```apt-get install python3```

## Testing Server

After running your server, you can run
```python3 ./gftestclient.py 5```
If you don't pass command line argument, default option tested would be 2


## Testing Client

```python3 ./gftestserver.py 3```
If you don't pass command line argument, default option tested would be 1


# Java test client for Multithreaded Getfile threading:

This test only sends invalid paths and does not validate the filename. The server should just return File Not Found.

## Installing Java
```apt-get install openjdk-8-jdk```

## Building

First, in this repository's root directory, create a folder called "classes":

```mkdir classes```

Then, build it:

```make```

## Running
```java -classpath ./classes/ edu.gatech.gios.MtgfTestClient number-of-workers min-delay max-delay```

Delays in milliseconds.

Example: A slow test for single-threaded operation:
```java -classpath ./classes/ edu.gatech.gios.MtgfTestClient 1 1000 1000```

Example: Stress test:
```java -classpath ./classes/ edu.gatech.gios.MtgfTestClient 1000 10 10```

# Workload generator:

The workload generator is a simple way of creating `workload.txt`, `content.txt`, and some files. This allows testing of multithreading clients and servers.
Note that the current `workload.c` only supports 100 lines.

```python3 ./gfworkload.py```

# IPC Stress Test

```python3 ./ipcstress.py /path/to/project/cache test-name```

Current tests:

`base` - the baseline test, get this to work first

`stress` - stress with an increasing number of threads but fixed parameters

`soak` - run for a long time with a fixed number of threads

`parameter` - tries variations on the parameters

Note: to save time on subsequent tests, if the test `.bin` files have already 
been created, the script does not re-generate them. To start the tests fresh 
with new `.bin` files, simply delete them from the `ipcstress_files` directory 
and the script will generate new ones.

# DFS Stress Test

```python3 ./dfsstress.py number-of-test-files /path/to/server/mount /path/to/client1/mount [/path/to/client2/mount...]```

Note: testing script needs to run after server is started and all clients are mounted (with command "mount"), and the paths should match the arguments in the testing tool's command
