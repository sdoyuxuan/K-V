// Copyright (c) 2016 QIHOO Inc
// Author: Lvpeng (lvpeng@360.cn)


#ifndef KVSTORE_DB_BLOCK_H_
#define KVSTORE_DB_BLOCK_H_

#include <string>
#include "db/block_meta.h"
#include "util/slice.h"
#include "util/status.h"

namespace kvstore{

class MmapReadableFile;
class Env;

}

namespace kvstore {

namespace db {

// block读取模块
// block文件格式为magic，data，entries，bucket，meta五段
// magic为校验位，meta为元信息
// data为序列化的value值，为了节约物理内存使用利用mmap文件load
// entries和bucket为序列化的hash桶，为了加速查询速度采用全内存结构
class Block {
 public:
  struct Entry {
    uint32_t hash;
    uint8_t key_length;
    uint32_t inner_offset;
    const char* key_data;
    uint64_t data_offset;
  };

  class Bucket {
   public:
    struct EntriesInfo {
      bool empty;
      uint64_t pos;
      uint64_t length;
    };
    Bucket() : data_(NULL), size_(0) { };
    Bucket(uint64_t* d, uint32_t n) : data_(d), size_(n) { };
    ~Bucket() { };
    inline EntriesInfo Get(uint32_t hash) const {
      EntriesInfo info;
      uint32_t i = hash & (size_ - 1); // size_ must be pow(2,N), so here is &
      assert(i < size_);
      info.pos = data_[i];
      info.length = data_[i+1] - data_[i];
      info.empty = info.length == 0;
      return info;
    };
    inline uint64_t size() const {
      return size_;
    };
   private:
    uint64_t* data_;
    uint32_t size_;
    uint64_t entries_length_;
  };

  Block(const char* idx_name);
  ~Block();

  bool Init();
  bool Destory();
  void printKeys();
  Status Get(const Slice& key, std::string* value);
  Status Get(const Slice& key, uint32_t key_hash, std::string* value);
  const Meta& meta() const { return meta_; };
  std::string ToString() const;

 private:
  bool InitData(Env* env);
  bool InitIndex(Env* env);
  bool CheckMagic(const Slice& smagic);
  bool InitMeta(const Slice& smeta);
  bool CheckMeta(uint64_t file_size);
  bool DecodeEntry(Slice* entries, Entry* e);

  std::string idx_name_;
  Meta meta_;
  Bucket bucket_;
  char* bucket_buf_;
  Slice entries_;
  char* entries_buf_;
  Slice data_;
  MmapReadableFile* dat_file_;
};

} // namespace db

} // namespace kvstore

#endif  // KVSTORE_DB_BLOCK_H_
