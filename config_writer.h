// Copyright (c) 2016 QIHOO Inc
// Author: xiongzhongting (xiongzhongting@360.cn)

#ifndef KVSTORE_UTIL_CONFIG_WRITER_H_
#define KVSTORE_UTIL_CONFIG_WRITER_H_

#include <fstream>
#include <sstream>

namespace kvstore {
namespace util {

class ConfigWriter {
 public:
  ConfigWriter() {}
  ~ConfigWriter() {}

  // 设置配置项
  template <class Type> void SetParameter(const std::string & p1,
                                          const std::string & p2,
                                          Type & t) {
    std::stringstream ss;
    ss << t;
    session_key_map_[p1][p2] = ss.str();
  }

  // 写入文件
  bool Write(const std::string& conf_file) {
    std::ofstream ofile(conf_file.c_str());
    if (!ofile) {
      return false;
    }

    std::map<SessionKey, SessionMap>::iterator kmit = session_key_map_.begin();
    std::map<SessionKey, SessionMap>::iterator kmend = session_key_map_.end();
    for (; kmit != kmend; ++ kmit) {
      ofile << "[" << kmit->first << "]" << std::endl;

      SessionMap::iterator mit = kmit->second.begin();
      SessionMap::iterator mend = kmit->second.end();
      for (; mit != mend; ++ mit) {
        ofile << mit->first << "=" << mit->second << std::endl;
      }
    }

    return true;
  }

 private:
  typedef std::string SessionKey;
  typedef std::map<std::string, std::string> SessionMap;
  std::map<SessionKey, SessionMap> session_key_map_;
};

}
}

#endif  // KVSTORE_UTIL_CONFIG_WRITER_H_
