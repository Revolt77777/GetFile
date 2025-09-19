#include <pthread.h>
#include <stdlib.h>

#include "gfserver-student.h"
#include "gfserver.h"
#include "workload.h"
#include "content.h"
#include "steque.h"

//
//  The purpose of this function is to handle a get request
//
//  The ctx is a pointer to the "context" operation and it contains connection state
//  The path is the path being retrieved
//  The arg allows the registration of context that is passed into this routine.
//  Note: you don't need to use arg. The test code uses it in some cases, but
//        not in others.
//
typedef struct {
	steque_t* queue;
	pthread_mutex_t* mutex;
	pthread_cond_t* cond;
}worker_args;

typedef struct {
	gfcontext_t *ctx;
	const char *path;
	void* arg;
}task_item_t;

worker_args* create_worker_args(steque_t* queue, pthread_mutex_t* mutex, pthread_cond_t* cond) {
	worker_args* arg = malloc(sizeof(worker_args));
	memset(arg, 0, sizeof(worker_args));
	arg->queue = queue;
	arg->mutex = mutex;
	arg->cond = cond;
	return arg;
}

void* worker_fn(void* arg) {
	worker_args* args = arg;
	while (1) {
		pthread_mutex_lock(args->mutex);
		while (steque_isempty(args->queue)) {
			pthread_cond_wait(args->cond, args->mutex);
		}

		steque_item item = steque_pop(args->queue);
		pthread_mutex_unlock(args->mutex);

		task_item_t* task = (task_item_t*)item;
		int fd = content_get(task->path);
		if (fd == -1) {
			gfs_sendheader(&task->ctx, GF_FILE_NOT_FOUND, 0);
			free(task);
		}
		else {
			struct stat file_stat;
			if (fstat(fd, &file_stat) == 0) {
				size_t file_size = file_stat.st_size;
				gfs_sendheader(&task->ctx, GF_OK, file_size);

				char buffer[8192];  // Fixed size buffer
				ssize_t bytes_read;

				off_t offset = 0;
				while (offset < file_size) {
					bytes_read = pread(fd, buffer, sizeof(buffer), offset);
					if (bytes_read <= 0) break;
					gfs_send(&task->ctx, buffer, bytes_read);
					offset += bytes_read;
				}
			} else {
				gfs_sendheader(&task->ctx, GF_ERROR, 0);
			}

			free(task);
		}
	}
}

gfh_error_t gfs_handler(gfcontext_t **ctx, const char *path, void* arg){
	worker_args *args = arg;
	steque_t* queue = args->queue;
	pthread_mutex_t* mutex = args->mutex;
	pthread_cond_t* cond = args->cond;

	task_item_t* task = malloc(sizeof(task_item_t));
	task->ctx = *ctx;
	*ctx = NULL;
	task->path = path;

	pthread_mutex_lock(mutex);
	steque_push(queue, task);
	pthread_cond_signal(cond);
	pthread_mutex_unlock(mutex);

	return gfh_success;
}

pthread_t* handler_pool_init(int nthreads, void* args) {
	pthread_t *tids = malloc(sizeof(pthread_t) * nthreads);

	for (int i = 0; i < nthreads; i++) {
		pthread_create(&tids[i], NULL, worker_fn, args);
	}

	return tids;
}





