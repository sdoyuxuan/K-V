#include "util/port_posix.h"

#include <cstdlib>
#include <stdio.h>
#include <string.h>

namespace kvstore {
namespace util {

static void PthreadCall(const char* label, int result) {
  if (result != 0) {
    fprintf(stderr, "pthread %s: %s\n", label, strerror(result));
    abort();
  }
}

Mutex::Mutex() { PthreadCall("init mutex", pthread_mutex_init(&mu_, NULL)); }

Mutex::~Mutex() { PthreadCall("destroy mutex", pthread_mutex_destroy(&mu_)); }

void Mutex::Lock() { PthreadCall("lock", pthread_mutex_lock(&mu_)); }

void Mutex::Unlock() { PthreadCall("unlock", pthread_mutex_unlock(&mu_)); }

CondVar::CondVar(Mutex* mu)
    : mu_(mu) {
    PthreadCall("init cv", pthread_cond_init(&cv_, NULL));
}

CondVar::~CondVar() { PthreadCall("destroy cv", pthread_cond_destroy(&cv_)); }

void CondVar::Wait() {
  PthreadCall("wait", pthread_cond_wait(&cv_, &mu_->mu_));
}

void CondVar::Signal() {
  PthreadCall("signal", pthread_cond_signal(&cv_));
}

void CondVar::SignalAll() {
  PthreadCall("broadcast", pthread_cond_broadcast(&cv_));
}

pthread_t Thread::pid() {
  return this->pid_;
}

void Thread::Run() {
  PthreadCall("thread create",pthread_create(&this->pid_, NULL, Thread::Func,
                                             reinterpret_cast<void *>(this)) );
}

bool Thread::Join() {
  return pthread_join(this->pid_, NULL) == 0;
}

void *Thread::Func(void *arg) {
  Thread *pthread = reinterpret_cast<Thread *>(arg);
  pthread->Start();
  return NULL;
}

void InitOnce(OnceType* once, void (*initializer)()) {
  PthreadCall("once", pthread_once(once, initializer));
}

}  // namespace util
}  // namespace kvstore
