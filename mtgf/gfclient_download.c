#include <pthread.h>
#include <stdlib.h>

#include "gfclient-student.h"
#include "steque.h"

#define MAX_THREADS 1024
#define PATH_BUFFER_SIZE 512

#define USAGE                                                             \
  "usage:\n"                                                              \
  "  gfclient_download [options]\n"                                       \
  "options:\n"                                                            \
  "  -h                  Show this help message\n"                        \
  "  -p [server_port]    Server port (Default: 29458)\n"                  \
  "  -t [nthreads]       Number of threads (Default 8 Max: 1024)\n"       \
  "  -w [workload_path]  Path to workload file (Default: workload.txt)\n" \
  "  -s [server_addr]    Server address (Default: 127.0.0.1)\n"           \
  "  -n [num_requests]   Request download total (Default: 16)\n"

/* OPTIONS DESCRIPTOR ====================================================== */
static struct option gLongOptions[] = {
    {"server", required_argument, NULL, 's'},
    {"port", required_argument, NULL, 'p'},
    {"help", no_argument, NULL, 'h'},
    {"nthreads", required_argument, NULL, 't'},
    {"workload", required_argument, NULL, 'w'},
    {"nrequests", required_argument, NULL, 'n'},
    {NULL, 0, NULL, 0}};

typedef struct {
  int active_workers;
  int shutdown;
  steque_t *queue;
  pthread_mutex_t* mutex;
  pthread_cond_t* worker_cond;
  pthread_cond_t* finish_cond;
  char *server;
  unsigned short port;
} worker_fn_args_t;

static void Usage() { fprintf(stderr, "%s", USAGE); }

static void localPath(char *req_path, char *local_path) {
  static int counter = 0;

  sprintf(local_path, "%s-%06d", &req_path[1], counter++);
}

static FILE *openFile(char *path) {
  char *cur, *prev;
  FILE *ans;

  /* Make the directory if it isn't there */
  prev = path;
  while (NULL != (cur = strchr(prev + 1, '/'))) {
    *cur = '\0';

    if (0 > mkdir(&path[0], S_IRWXU)) {
      if (errno != EEXIST) {
        perror("Unable to create directory");
        exit(EXIT_FAILURE);
      }
    }

    *cur = '/';
    prev = cur;
  }

  if (NULL == (ans = fopen(&path[0], "w"))) {
    perror("Unable to open file");
    exit(EXIT_FAILURE);
  }

  return ans;
}

/* Callbacks ========================================================= */
static void writecb(void *data, size_t data_len, void *arg) {
  FILE *file = (FILE *)arg;
  fwrite(data, 1, data_len, file);
}

// Worker function of each thread
void* worker_fn(void* arg) {
  worker_fn_args_t *args = (worker_fn_args_t*)arg;
  int returncode = 0;
  char *req_path = NULL;
  char local_path[PATH_BUFFER_SIZE];
  gfcrequest_t *gfr = NULL;
  FILE *file = NULL;

  while (1) {
    // Lock mutex and claim a task
    pthread_mutex_lock(args->mutex);
    while (args->shutdown == 0 && steque_isempty(args->queue)) {
      pthread_cond_wait(args->worker_cond, args->mutex);
    }
    if (args->shutdown == 1) {
      pthread_mutex_unlock(args->mutex);
      pthread_exit(NULL);
    }
    req_path = steque_pop(args->queue);
    args->active_workers++;
    pthread_mutex_unlock(args->mutex);

    // Actual working logic
    if (strlen(req_path) > PATH_BUFFER_SIZE) {
      fprintf(stderr, "Request path exceeded maximum of %d characters\n.", PATH_BUFFER_SIZE);
      pthread_mutex_lock(args->mutex);
      args->active_workers--;
      if (steque_isempty(args->queue) && args->active_workers == 0) {
        pthread_cond_signal(args->finish_cond);
      }
      pthread_mutex_unlock(args->mutex);
      continue;
    }

    localPath(req_path, local_path);

    file = openFile(local_path);

    gfr = gfc_create();
    gfc_set_path(&gfr, req_path);

    gfc_set_port(&gfr, args->port);
    gfc_set_server(&gfr, args->server);
    gfc_set_writearg(&gfr, file);
    gfc_set_writefunc(&gfr, writecb);

    fprintf(stdout, "Requesting %s%s\n", args->server, req_path);

    if (0 > (returncode = gfc_perform(&gfr))) {
      fprintf(stderr, "gfc_perform returned an error %d\n", returncode);
      fclose(file);
      if (0 > unlink(local_path))
        fprintf(stderr, "warning: unlink failed on %s\n", local_path);
    } else {
      fclose(file);
    }

    if (gfc_get_status(&gfr) != GF_OK) {
      if (0 > unlink(local_path)) {
        fprintf(stderr, "warning: unlink failed on %s\n", local_path);
      }
    }

    //fprintf(stdout, "Status: %s\n", gfc_strstatus(gfc_get_status(&gfr)));
    fprintf(stdout, "Received %zu of %zu bytes of %s\n", gfc_get_bytesreceived(&gfr),
    gfc_get_filelen(&gfr), req_path);

    gfc_cleanup(&gfr);

    /*
       * note that when you move the above logic into your worker thread, you will
       * need to coordinate with the boss thread here to effect a clean shutdown.
       */

    // Work done
    pthread_mutex_lock(args->mutex);
    args->active_workers--;
    if (steque_isempty(args->queue) && args->active_workers == 0) {
      pthread_cond_signal(args->finish_cond);
    }
    pthread_mutex_unlock(args->mutex);
  }
}

/* Main ========================================================= */
int main(int argc, char **argv) {
  /* COMMAND LINE OPTIONS ============================================= */
  char *workload_path = "workload.txt";
  char *server = "localhost";
  unsigned short port = 29458;
  int option_char = 0;
  int nthreads = 8;
  int nrequests = 14;

  setbuf(stdout, NULL);  // disable caching

  // Parse and set command line arguments
  while ((option_char = getopt_long(argc, argv, "p:n:hs:t:r:w:", gLongOptions,
                                    NULL)) != -1) {
    switch (option_char) {

      case 'w':  // workload-path
        workload_path = optarg;
        break;
      case 's':  // server
        server = optarg;
        break;
      case 'r': // nrequests
      case 'n': // nrequests
        nrequests = atoi(optarg);
        break;
      case 'p':  // port
        port = atoi(optarg);
        break;
      case 't':  // nthreads
        nthreads = atoi(optarg);
        break;
      default:
        Usage();
        exit(1);


      case 'h':  // help
        Usage();
        exit(0);
    }
  }

  if (EXIT_SUCCESS != workload_init(workload_path)) {
    fprintf(stderr, "Unable to load workload file %s.\n", workload_path);
    exit(EXIT_FAILURE);
  }
  if (port > 65331) {
    fprintf(stderr, "Invalid port number\n");
    exit(EXIT_FAILURE);
  }
  if (nthreads < 1 || nthreads > MAX_THREADS) {
    fprintf(stderr, "Invalid amount of threads\n");
    exit(EXIT_FAILURE);
  }
  gfc_global_init();

  // add your threadpool creation here
  pthread_mutex_t mutex;
  pthread_cond_t worker_cond;
  pthread_cond_t finish_cond;
  pthread_mutex_init(&mutex, NULL);
  pthread_cond_init(&worker_cond, NULL);
  pthread_cond_init(&finish_cond, NULL);

  steque_t queue;
  steque_init(&queue);
  for (int i = 0; i < nrequests; i++) {
    char *path = workload_get_path();
    steque_push(&queue, path);
  }

  worker_fn_args_t arg = {0};

  arg.shutdown = 0;
  arg.active_workers = 0;
  arg.server = server;
  arg.port = port;
  arg.worker_cond = &worker_cond;
  arg.finish_cond = &finish_cond;
  arg.mutex = &mutex;
  arg.queue = &queue;
  arg.active_workers = 0;

  pthread_t *tids = malloc(sizeof(pthread_t) * nthreads);

  for (int i = 0; i < nthreads; i++) {
    pthread_create(&tids[i], NULL, worker_fn, &arg);
  }

  pthread_mutex_lock(arg.mutex);
  pthread_cond_broadcast(&worker_cond);

  while (!steque_isempty(&queue) || arg.active_workers > 0) {
    pthread_cond_wait(&finish_cond, &mutex);
  }
  fprintf(stdout, "All tasks finished\n");
  arg.shutdown = 1;
  pthread_cond_broadcast(&worker_cond);
  pthread_mutex_unlock(&mutex);

  for (int i = 0; i < nthreads; i++) {
    pthread_join(tids[i], NULL);
  }
  pthread_mutex_destroy(&mutex);
  pthread_cond_destroy(&worker_cond);
  pthread_cond_destroy(&finish_cond);
  steque_destroy(&queue);
  free(tids);
  gfc_global_cleanup();  /* use for any global cleanup for AFTER your thread
                          pool has terminated. */
  return 0;
}
