// Copyright (c) 2016 QIHOO Inc
// Author: xiongzhongting (xiongzhongting@360.cn)

#ifndef KVSTORE_UTIL_CONFIG_PARSE_H_
#define KVSTORE_UTIL_CONFIG_PARSE_H_

#include <string>
#include <vector>
#include <map>

namespace qihoo {
namespace ad {
class ConfigReader;
}
}

namespace kvstore {
namespace util {

struct LogInfo {
  std::string dir;
  int level;
};

struct NodeInfo {
  std::string ip;
  int port;
  std::vector<std::string> storages;
};

struct PartitionInfo {
  int group_belong;
  std::vector<std::pair<int, int> > destinations;
};

struct ClientInfo {
  int conn_timeout;
  int recv_timeout;
  int send_timeout;
  int max_retries;
};

class ConfigWriter;

// 提取group信息
// GROUPS : {count, group0, group1}
bool ExtractGroupInfo(qihoo::ad::ConfigReader& conf_reader,
                      std::vector<std::vector<uint32_t> >& group_clients);

// 生成group配置信息
// 格式同上
void FormatGroupInfo(ConfigWriter& conf_writer,
                     const std::vector<std::vector<uint32_t> >& group_clients);

// 提取node数量
// NODES : count
bool ExtractNodeCount(qihoo::ad::ConfigReader& conf_reader, int& count);

// 提取node信息
// NODES : count
// NODE0 ：{ip, port}
bool ExtractNodeInfo(qihoo::ad::ConfigReader& conf_reader,
                     std::map<uint32_t, NodeInfo>& nodes);

// 生成node配置信息
// 格式同上
void FormatNodeInfo(ConfigWriter& conf_writer,
                    const std::vector<NodeInfo>& nodes);

// 提取partition数量
// PARTITIONS : count
bool ExtractPartitionCount(qihoo::ad::ConfigReader& conf_reader, int& count);

// 提取partition信息
// PARTITIONS : count
// PARTITION0 : group
bool ExtractPartitionInfo(qihoo::ad::ConfigReader& conf_reader,
                          std::vector<uint32_t>& partition_group_map);

// 生成partition配置信息
// 格式同上
void FormatPartitionInfo(ConfigWriter& conf_writer,
                         const std::vector<PartitionInfo>& partitions);

// 提取client信息
// CLIENT ：{conn_timeout, recv_timeout, send_timeout, max_retries}
bool ExtractClientInfo(qihoo::ad::ConfigReader& conf_reader,
                       ClientInfo& client_info, bool strict = false);

// 生成client配置信息
// 格式同上
void FormatClientInfo(ConfigWriter& conf_writer,
                      const kvstore::util::ClientInfo& client_info);

// 提取server信息
// SERVER ：{ip, port}
bool ExtractServerInfo(qihoo::ad::ConfigReader& conf_reader,
                       NodeInfo& node_info, bool strict = false);

// 提取日志信息
// LOG ：{dir, level}
bool ExtractLogInfo(qihoo::ad::ConfigReader& conf_reader,
                    LogInfo& log_info, bool strict = false);

// 提取table配置路径
// TABLE ：{conf_path}
bool ExtractTableConfPath(qihoo::ad::ConfigReader& conf_reader,
                          std::string& conf_path, bool strict = false);

// 提取storage area信息
// STORAGES : count
// STORAGE0 : path
bool ExtractStorageAreaList(qihoo::ad::ConfigReader& conf_reader,
                            std::vector<std::string>& storage_area_list);

// 提取storage area信息
// TABLES : count
// TABLE0 : name
bool ExtractTableNameList(qihoo::ad::ConfigReader& conf_reader,
                          std::vector<std::string>& table_name_list);

}
}

#endif  // KVSTORE_UTIL_CONFIG_PARSE_H_
