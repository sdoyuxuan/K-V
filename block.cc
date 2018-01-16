// Copyright (c) 2016 QIHOO Inc
// Author: Lvpeng (lvpeng@360.cn)

#include "db/block.h"
#include <iostream>
#include <boost/shared_ptr.hpp>
#include "util/env.h"
#include <glog/logging.h>
#include "db/options.h"
#include "util/env.h"
#include "util/coding.h"
#include "util/hash.h"
#include "util/port_posix.h"
#include "util/util.h"
#include "util/zlib_compress.h"

using namespace std;

namespace kvstore {

namespace db {

Block::Block(const char* idx_name)
    : idx_name_(idx_name),
      bucket_buf_(NULL),
      entries_buf_(NULL),
      dat_file_(NULL) {
  memset(&meta_, 0, sizeof(Meta));
}

Block::~Block() {
}

bool Block::InitData(Env* env) {
  Status s;
  s = env->NewMmapReadableFile(idx_name_,
                               meta_.magic_length + meta_.data_length,
                               0,
                               &dat_file_);
  if (!s.ok()) {
    LOG(ERROR) << "NewMmapReadableFile: " << idx_name_ << "error: " << s.ToString();
    return false;
  }
  // data_ is built in mmap memory
  data_ = dat_file_->Mmap();
  data_.remove_prefix(meta_.magic_length);
  if (meta_.data_length != data_.size()) {
    LOG(ERROR) << "expect dat size: " << meta_.data_length <<
        ", but: " << data_.size();
    return false;
  }
  return true;
}

bool Block::InitIndex(Env* env) {
  Status s;
  uint64_t file_size;
  s = env->GetFileSize(idx_name_, &file_size);
  if (!s.ok()) {
    LOG(ERROR) << "GetFileSize: " << idx_name_;
    return false;
  }
  uint32_t min_idx_len = 4 + sizeof(Meta); // magic + meta
  if (file_size < min_idx_len) {
    LOG(ERROR) << "too small idx file: " << idx_name_;
    return false;
  }
  RandomAccessFile* pidx_file;
  s = env->NewRandomAccessFile(idx_name_, &pidx_file);
  if (!s.ok()) {
    LOG(ERROR) << "RandomAccessFile: " << idx_name_;
    return false;
  }
  boost::shared_ptr<RandomAccessFile> idx_file(pidx_file);
  char scratch[min_idx_len];
  Slice result;
  s = idx_file->Read(0, 4, &result, scratch);
  if (!s.ok()) {
    LOG(ERROR) << "read magic: " << idx_name_;
    return false;
  }
  if (!CheckMagic(result)) {
    LOG(ERROR) << "unknown magic: " << idx_name_;
    return false;
  }
  s = idx_file->Read(file_size - sizeof(Meta), sizeof(Meta), &result, scratch);
  if (!s.ok()) {
    LOG(ERROR) << "read meta: " << idx_name_;
    return false;
  }
  if (!InitMeta(result)) {
    LOG(ERROR) << "init meta: " << idx_name_;
    return false;
  }
  if (!CheckMeta(file_size)) {
    LOG(ERROR) << "init meta: " << idx_name_;
    return false;
  }
  // read entries to malloc memory
  entries_buf_ = reinterpret_cast<char*>(malloc(meta_.entries_length));
  s = idx_file->Read(meta_.magic_length + meta_.data_length,
                     meta_.entries_length, &result, entries_buf_);
  if (!s.ok() || result.size() != meta_.entries_length) {
    LOG(ERROR) << "read entries: " << idx_name_;
    return false;
  }
  entries_ = Slice(entries_buf_, meta_.entries_length);
  // read bucket to malloc memory
  bucket_buf_ = reinterpret_cast<char*>(malloc(meta_.bucket_length));
  s = idx_file->Read(meta_.magic_length + meta_.data_length +
                                          meta_.entries_length,
                     meta_.bucket_length, &result, bucket_buf_);
  if (!s.ok() || result.size() != meta_.bucket_length) {
    LOG(ERROR) << "read bucket: " << idx_name_;
    return false;
  }
  assert(meta_.bucket_length % sizeof(uint64_t) == 0);
  bucket_ = Bucket(reinterpret_cast<uint64_t*>(bucket_buf_),
                   meta_.hash_table_length);
  return true;
}

bool Block::CheckMeta(uint64_t file_size) {
  uint64_t expect_file_size = meta_.magic_length + meta_.data_length +
      meta_.entries_length + meta_.bucket_length + meta_.meta_length;
  if (expect_file_size != file_size) {
    LOG(ERROR) << "expect idx size: " << expect_file_size <<
        ", but: " << file_size;
    return false;
  }
  if (meta_.bucket_length != (meta_.hash_table_length + 1) * sizeof(uint64_t)) {
    LOG(ERROR) << "bucket size: " << meta_.hash_table_length <<
        ", but bucket length: " << meta_.bucket_length;
    return false;
  }
  return true;
}

bool Block::InitMeta(const Slice& smeta) {
  if (smeta.size() != sizeof(Meta)) {
    return false;
  }
  memcpy(&meta_, smeta.data(), sizeof(Meta));
  return true;
}

bool Block::CheckMagic(const Slice& smagic) {
  if (smagic.size() != 4) {
    return false;
  }
  uint32_t magic = DecodeFixed32(smagic.data());
  return magic == kMagic;
}

bool Block::Init() {
  Env* env = Env::Default();
  assert(env);
  if (!InitIndex(env)) {
    LOG(ERROR) << "InitIndex";
    return false;
  }
  if (!InitData(env)) {
    LOG(ERROR) << "InitData";
    return false;
  }
  return true;
}

bool Block::Destory() {
  if (dat_file_) {
    delete dat_file_;
    dat_file_ = NULL;
  }
  if (bucket_buf_) {
    free(bucket_buf_);
    bucket_buf_ = NULL;
  }
  if (entries_buf_) {
    free(entries_buf_);
    entries_buf_ = NULL;
  }
  return true;
}

Status Block::Get(const Slice& key, string* value) {
  uint32_t hash = Hash(key.data(), key.size(), 0);
  return Get(key, hash, value);
}

// 查询过程描述：
// 1、查询key hash求模
// 2、bucket段查找entries段起始地址
// 3、entries段为序列化的倒链，比较keyhash和key
// 4、如果查找到继续去mmap的数据文件中读取value值并返回
// 5、如果查不到返回notfound
Status Block::Get(const Slice& key, uint32_t key_hash, string* value) {
  assert(value != NULL);
  Bucket::EntriesInfo entries_info = bucket_.Get(key_hash);
  if (entries_info.pos + entries_info.length > entries_.size()) {
    return Status::Corruption("entries_pos + entries_length > entries_.size()");
  }
  if (entries_info.empty) {
    return Status::NotFound(key);
  }
  Slice entries = entries_;
  entries.remove_prefix(entries_info.pos);
  entries.resize(entries_info.length);
  Entry e;
  uint32_t count = 0;
  while (true) {
    if (entries.size() == 0) {
      break;
    }
    count++;
    assert(count <= meta_.max_list_length);
    if (!DecodeEntry(&entries, &e)) {
      return Status::Corruption("decode entry", key);
    }
    Slice decode_key = Slice(e.key_data, e.key_length);
    if (e.hash == key_hash && decode_key == key) {
      Slice data = data_;
      data.remove_prefix(e.data_offset);
      Slice raw_value;
      if (!GetLengthPrefixedSlice(&data, &raw_value)) {
        return Status::Corruption("GetLengthPrefixedSlice data");
      }
      value->clear();
      if (meta_.compress == kSnappy) { // snappy
        size_t length = 0;
        util::Snappy_GetUncompressedLength(raw_value.data(),
                                           raw_value.size(),
                                           &length);
        value->resize(length);
        util::Snappy_Uncompress(raw_value.data(), raw_value.size(),
                          const_cast<char*>(value->data()));
      } else if (meta_.compress == kNoCompress) { // no compress
        value->assign(raw_value.data(), raw_value.size());
      } else {
        string segment;
        if (meta_.compress == kSegmentSnappy) { // segment snappy
          size_t length = 0;
          util::Snappy_GetUncompressedLength(raw_value.data(),
                                           raw_value.size(),
                                           &length);
          segment.resize(length);
          util::Snappy_Uncompress(raw_value.data(), raw_value.size(),
                                  const_cast<char*>(segment.data()));
        }
        else if (meta_.compress == kSegmentZlib) { // segment zlib
          uint32_t length = 0;
          if (!GetVarint32(&raw_value, &length)) {
            return Status::Corruption("GetVarint32 raw value");
          }
          string raw_str(raw_value.data(), raw_value.size());
          util::Zlib_Uncompress(raw_str, length, segment);
        }
        Slice seg_slice(segment);
        seg_slice.remove_prefix(e.inner_offset);
        Slice element;
        if (!GetLengthPrefixedSlice(&seg_slice, &element)) {
          return Status::Corruption("GetLengthPrefixedSlice element");
        }
        value->assign(element.data(), element.size());
      }
      return Status::OK();
    }
  }
  return Status::NotFound(key);
}

void Block::printKeys() {
  Slice entries = entries_;
  Entry e;
  while (true) {
    if (entries.size() == 0) {
      break;
    }
    if (!DecodeEntry(&entries, &e)) {
      std::cerr << "decode error." << std::endl;
      break;
    }
    Slice decode_key = Slice(e.key_data, e.key_length);
    std::cout << decode_key.ToString() << std::endl;
  }
}

bool Block::DecodeEntry(Slice* entries, Entry* e) {
  if (!GetFixed32(entries, &e->hash)) {
    return false;
  }
  if (!GetVarint64(entries, &e->data_offset)) {
  // if (!GetFixed64(entries, &e->data_offset)) {
    return false;
  }
  if (meta_.compress > kSnappy) {
    if (!GetVarint32(entries, &e->inner_offset)) {
      return false;
    }
  }
  if (!GetFixed8(entries, &e->key_length)) {
    return false;
  }
  if (entries->size() < e->key_length) {
    return false;
  }
  e->key_data = entries->data();
  entries->remove_prefix(e->key_length);
  return true;
}

string Block::ToString() const {
  return meta_.ToString();
}

} // namespace db

} // namespace kvstore

