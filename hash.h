#ifndef KVSTORE_UTIL_HASH_H_
#define KVSTORE_UTIL_HASH_H_

#include <stddef.h>
#include <stdint.h>

namespace kvstore {

extern uint32_t Hash(const char* data, size_t n, uint32_t seed);

}

#endif  // KVSTORE_UTIL_HASH_H_
