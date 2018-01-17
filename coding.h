#ifndef KVSTORE_UTIL_CODING_H_
#define KVSTORE_UTIL_CODING_H_

#include <stdint.h>
#include <string.h>
#include <string>
#include "util/slice.h"

namespace kvstore {

// Standard Put... routines append to a string
extern uint32_t PutFixed8(std::string* dst, uint8_t value);
extern uint32_t PutFixed16(std::string* dst, uint16_t value);
extern uint32_t PutFixed32(std::string* dst, uint32_t value);
extern uint32_t PutFixed64(std::string* dst, uint64_t value);
extern uint32_t PutVarint32(std::string* dst, uint32_t value);
extern uint32_t PutVarint64(std::string* dst, uint64_t value);
extern uint32_t PutLengthPrefixedSlice(std::string* dst, const Slice& value);

// Standard Get... routines parse a value from the beginning of a Slice
// and advance the slice past the parsed value.
extern bool GetVarint32(Slice* input, uint32_t* value);
extern bool GetVarint64(Slice* input, uint64_t* value);
extern bool GetLengthPrefixedSlice(Slice* input, Slice* result);

// Pointer-based variants of GetVarint...  These either store a value
// in *v and return a pointer just past the parsed value, or return
// NULL on error.  These routines only look at bytes in the range
// [p..limit-1]
extern const char* GetVarint32Ptr(const char* p,const char* limit, uint32_t* v);
extern const char* GetVarint64Ptr(const char* p,const char* limit, uint64_t* v);

// Returns the length of the varint32 or varint64 encoding of "v"
extern int VarintLength(uint64_t v);

// Lower-level versions of Put... that write directly into a character buffer
// REQUIRES: dst has enough space for the value being written
extern void EncodeFixed8(char* dst, uint8_t value);
extern void EncodeFixed16(char* dst, uint16_t value);
extern void EncodeFixed32(char* dst, uint32_t value);
extern void EncodeFixed64(char* dst, uint64_t value);

// Lower-level versions of Put... that write directly into a character buffer
// and return a pointer just past the last byte written.
// REQUIRES: dst has enough space for the value being written
extern char* EncodeVarint32(char* dst, uint32_t value);
extern char* EncodeVarint64(char* dst, uint64_t value);

inline uint8_t DecodeFixed8(const char* ptr) {
  uint8_t result;
  memcpy(&result, ptr, sizeof(result));  // gcc optimizes this to a plain load
  return result;
}

inline uint16_t DecodeFixed16(const char* ptr) {
  uint16_t result;
  memcpy(&result, ptr, sizeof(result));  // gcc optimizes this to a plain load
  return result;
}

inline uint32_t DecodeFixed32(const char* ptr) {
  // Load the raw bytes
  uint32_t result;
  memcpy(&result, ptr, sizeof(result));  // gcc optimizes this to a plain load
  return result;
}

inline uint64_t DecodeFixed64(const char* ptr) {
  // Load the raw bytes
  uint64_t result;
  memcpy(&result, ptr, sizeof(result));  // gcc optimizes this to a plain load
  return result;
}

inline bool GetFixed8(Slice* input, uint8_t* value) {
  if (input->size() < 1) {
    return false;
  }
  *value = DecodeFixed8(input->data());
  input->remove_prefix(1);
  return true;
}

inline bool GetFixed16(Slice* input, uint16_t* value) {
  if (input->size() < 2) {
    return false;
  }
  *value = DecodeFixed16(input->data());
  input->remove_prefix(2);
  return true;
}

inline bool GetFixed32(Slice* input, uint32_t* value) {
  if (input->size() < 4) {
    return false;
  }
  *value = DecodeFixed32(input->data());
  input->remove_prefix(4);
  return true;
}

inline bool GetFixed64(Slice* input, uint64_t* value) {
  if (input->size() < 8) {
    return false;
  }
  *value = DecodeFixed64(input->data());
  input->remove_prefix(8);
  return true;
}

// Internal routine for use by fallback path of GetVarint32Ptr
extern const char* GetVarint32PtrFallback(const char* p,
                                          const char* limit,
                                          uint32_t* value);
inline const char* GetVarint32Ptr(const char* p,
                                  const char* limit,
                                  uint32_t* value) {
  if (p < limit) {
    uint32_t result = *(reinterpret_cast<const unsigned char*>(p));
    if ((result & 128) == 0) {
      *value = result;
      return p + 1;
    }
  }
  return GetVarint32PtrFallback(p, limit, value);
}

}  // namespace kvstore

#endif  // KVSTORE_UTIL_CODING_H_
