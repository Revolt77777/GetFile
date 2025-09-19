package edu.gatech.gios;

import java.util.Random;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.net.Socket;
import java.net.ConnectException;
import java.io.IOException;
import java.io.OutputStream;
import java.io.InputStream;

/**
 * Multithreaded GetFile Test Client by Miguel Paraz <mparaz@gatech.edu>
 * Command line: number-of-workers minimum-delay-in-milliseconds maximum-delay
 */
public class MtgfTestClient implements Runnable {
    private final int workerId;
    private final int minDelay, maxDelay;

    public MtgfTestClient(int workerId, int minDelay, int maxDelay) {
        this.workerId = workerId;
        this.minDelay = minDelay;
        this.maxDelay = maxDelay;
    }

    public static void main(String[] args) throws InterruptedException {
        final int workers = Integer.parseInt(args[0]);
        final int minDelay = Integer.parseInt(args[1]);
        final int maxDelay = Integer.parseInt(args[2]);

        final ExecutorService executorService = Executors.newFixedThreadPool(workers);

        for (int i = 0; i < workers; i++) {
            executorService.execute(new MtgfTestClient(i, minDelay, maxDelay));
        }

        // Just wait indefiniteiy...
        Thread.sleep(86400);
    }

    @Override
    public void run() {
        final Random random = new Random();

        // Just send a nonexistent path. We're not testing I/O.
        final String header = "GETFILE GET /worker" + workerId + "\r\n\r\n";
        
        while (true) {
            final byte[] buffer = new byte[8192];

            try {
                final Socket socket = new Socket("127.0.0.1", 10823);
                final OutputStream outputStream = socket.getOutputStream();
                final InputStream inputStream = socket.getInputStream();

                outputStream.write(header.getBytes());

                inputStream.read(buffer);
                inputStream.close();

                // Delay
                final int delay;
                if (minDelay == maxDelay) {
                    delay = minDelay;
                } else {
                    delay = random.nextInt(maxDelay - minDelay) + minDelay;
                }

            Thread.sleep(delay);

            } catch (ConnectException e) {
                // The server is dead, just shut down worker.
                e.printStackTrace();
                return;
            } catch (IOException e) {
                // The socket is dead, reopen.
                e.printStackTrace();
            } catch (InterruptedException e) {
                // Shut down worker.
                e.printStackTrace();
                return;
            }
        }
    }
}
