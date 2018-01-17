// Copyright (c) 2017 QIHOO Inc
// Author: xiongzhongting (xiongzhongting@360.cn)

#ifndef KVSTORE_UTIL_ZLIB_COMPRESS_H_
#define KVSTORE_UTIL_ZLIB_COMPRESS_H_

#include <string>

namespace kvstore {
namespace util {

void Zlib_Compress(std::string& in, std::string& out);
void Zlib_Uncompress(std::string& in, size_t raw_len, std::string& out);

} // namespace util
} // namespace kvstore

#endif  // KVSTORE_UTIL_ZLIB_COMPRESS_H_

