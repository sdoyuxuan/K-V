// Copyright (c) 2016 QIHOO Inc
// Author: Lvpeng (lvpeng@360.cn)


#ifndef KVSTORE_UTIL_ITERATOR_H_
#define KVSTORE_UTIL_ITERATOR_H_

namespace kvstore {

class Iterator {
 public:
  virtual ~Iterator() { };
  virtual bool Valid() = 0;
  virtual void Next() = 0;
  virtual Slice Key() = 0;
  virtual Slice Value() = 0;
};

}

#endif  // KVSTORE_UTIL_ITERATOR_H_

