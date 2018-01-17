#ifndef KVSTORE_UTIL_PORT_POSIX_H_
#define KVSTORE_UTIL_PORT_POSIX_H_

#include <pthread.h>
#include <snappy.h>
#include <stdint.h>
#include <string>

namespace kvstore {
namespace util {

class CondVar;

class Mutex {
 public:
  Mutex();
  ~Mutex();

  void Lock();
  void Unlock();
  void AssertHeld() { }

 private:
  friend class CondVar;
  pthread_mutex_t mu_;

  // No copying
  Mutex(const Mutex&);
  void operator=(const Mutex&);
};

class CondVar {
 public:
  explicit CondVar(Mutex* mu);
  ~CondVar();
  void Wait();
  void Signal();
  void SignalAll();
 private:
  pthread_cond_t cv_;
  Mutex* mu_;
};

class MutexLock {
 public:
  explicit MutexLock(Mutex *mu)
      : mu_(mu)  {
    this->mu_->Lock();
  }
  ~MutexLock() { this->mu_->Unlock(); }

 private:
  Mutex *const mu_;
  // No copying allowed
  MutexLock(const MutexLock&);
  void operator=(const MutexLock&);
};

class Thread
{
 public:
  virtual ~Thread() {}
  void Run();
  bool Join();
  pthread_t pid();
 protected:
  virtual void Start() = 0;
  static void *Func(void *arg);
 private:
  pthread_t pid_;
};

typedef pthread_once_t OnceType;
#define ONCE_INIT PTHREAD_ONCE_INIT

extern void InitOnce(OnceType *once, void (*initializer)());

inline bool Snappy_Compress(const char* input, size_t length,
                            ::std::string* output) {
  output->resize(snappy::MaxCompressedLength(length));
  size_t outlen;
  snappy::RawCompress(input, length, &(*output)[0], &outlen);
  output->resize(outlen);
  return true;
}

inline bool Snappy_GetUncompressedLength(const char* input, size_t length,
                                         size_t* result) {
  return snappy::GetUncompressedLength(input, length, result);
}

inline bool Snappy_Uncompress(const char* input, size_t length,
                              char* output) {
  return snappy::RawUncompress(input, length, output);
}

}  // namespace util
}  // namespace kvstore

#endif  // KVSTORE_UTIL_PORT_POSIX_H_
