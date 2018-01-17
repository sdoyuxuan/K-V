// Copyright (c) 2017 QIHOO Inc
// Author: xiongzhongting (xiongzhongting@360.cn)

#include <zlib.h>
#include <string>

namespace kvstore {
namespace util {

void Zlib_Compress(std::string& in, std::string& out) {
  size_t l = compressBound(in.length());
  out.resize(l);
  compress((Bytef*)&out[0], &l, (const Bytef*)in.data(), in.length());
  out.resize(l);
}

void Zlib_Uncompress(std::string& in, size_t raw_len, std::string& out) {
  out.resize(raw_len);
  uncompress((Bytef*)out.data(), &raw_len, (const Bytef*)in.data(), in.length());
}

} // namespace util
} // namespace kvstore
