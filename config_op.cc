// Copyright (c) 2016 QIHOO Inc
// Author: xiongzhongting (xiongzhongting@360.cn)

#include <sstream>
#include <boost/lexical_cast.hpp>
#include <glog/logging.h>
#include "ConfigReader.h"
#include "config_writer.h"
#include "config_op.h"

namespace kvstore {
namespace util {

// 配置文件section最大长度
const int section_name_length = 32;

// 缺省连接超时(15ms)
const int default_conn_timeout = 15;

// 缺省接收超时(10ms)
const int default_recv_timeout = 10;

// 缺省发送超时(5ms)
const int default_send_timeout = 5;

// 缺省最大重试次数(3次)
const int default_max_retries = 3;

// 分隔符
const std::string level0_delim(",");
const std::string level1_delim(":");

// 缺省服务器配置
const std::string default_server_ip("127.0.0.1");
const int default_server_port = 8090;

// 缺省log配置
const std::string default_log_dir = "log/";
const int default_log_level = google::ERROR;

// 缺省表配置文件
const std::string default_table_conf = "conf/table.conf";

// 配置文件section名
const std::string conf_section_storages("STORAGES");
const std::string conf_field_count("count");
const std::string conf_section_storage("STORAGE");
const std::string conf_field_path("path");
const std::string conf_section_tables("TABLES");
const std::string conf_section_table("TABLE");
const std::string conf_field_name("name");

const std::string conf_section_groups("GROUPS");
const std::string conf_field_group("group");
const std::string conf_section_nodes("NODES");
const std::string conf_section_node("NODE");
const std::string conf_field_ip("ip");
const std::string conf_field_port("port");
const std::string conf_field_storage("storage");
const std::string conf_section_partitions("PARTITIONS");
const std::string conf_section_partition("PARTITION");
const std::string conf_field_storages("storages");

const std::string conf_section_client("CLIENT");
const std::string conf_field_conn_timeout("conn_timeout");
const std::string conf_field_recv_timeout("recv_timeout");
const std::string conf_field_send_timeout("send_timeout");
const std::string conf_field_max_retries("max_retries");

const std::string conf_section_server = "SERVER";
const std::string conf_section_log = "LOG";
const std::string conf_field_dir = "dir";
const std::string conf_field_level = "level";
const std::string conf_field_conf = "conf_path";

// 提取group信息
// GROUPS : {count, group0, group1}
bool ExtractGroupInfo(qihoo::ad::ConfigReader& conf_reader,
                      std::vector<std::vector<uint32_t> >& group_clients) {
  std::vector<std::vector<uint32_t> > tmp_group_clients;

  int group_count = 0;
  if (!conf_reader.getParameter(conf_section_groups,
                                conf_field_count, group_count)) {
    LOG(ERROR) << "group count not set!";
    return false;
  }

  tmp_group_clients.resize(group_count);
  char field_name[section_name_length] = {0};
  for (int i = 0; i < group_count; i++) {
    std::string group;
    snprintf(field_name, section_name_length, "%s%d",
             conf_field_group.c_str(), i);
    if(!conf_reader.getParameter(conf_section_groups, field_name, group)) {
      LOG(ERROR) << field_name << " not found!";
      return false;
    }

    std::vector<std::string> group_info;
    boost::algorithm::split(group_info, group, boost::is_any_of(","));
    std::vector<std::string>::iterator it = group_info.begin();
    std::vector<std::string>::iterator end = group_info.end();
    for (; it != end; ++it) {
      uint32_t client = 0;
      try {
        client = boost::lexical_cast<uint32_t>(*it);
      }
      catch (boost::bad_lexical_cast& e) {
        LOG(ERROR) << "invalid client id found!id:" << *it;
        return false;
      }

      tmp_group_clients[i].push_back(client);
    }
  }

  group_clients.swap(tmp_group_clients);
  return true;
}

// 生成group配置信息
// 格式同上
void FormatGroupInfo(ConfigWriter& conf_writer,
                     const std::vector<std::vector<uint32_t> >& group_clients) {
  size_t group_count = group_clients.size();
  conf_writer.SetParameter(conf_section_groups, conf_field_count, group_count);

  std::vector<std::vector<uint32_t> >::const_iterator git =
      group_clients.begin();
  std::vector<std::vector<uint32_t> >::const_iterator gend =
      group_clients.end();
  int group_index = 0;
  for (; git != gend; ++git) {
    std::stringstream group;
    group << conf_field_group << group_index++;

    std::stringstream nodes;
    std::vector<uint32_t>::const_iterator it = git->begin();
    std::vector<uint32_t>::const_iterator end = git->end();
    for (;;) {
      nodes << *it;
      if (++it == end) {
        break;
      }
      nodes << level0_delim;
    }

    std::string str_nodes(nodes.str());
    conf_writer.SetParameter(conf_section_groups, group.str(), str_nodes);
  }
}

// 提取node数量
// NODES : count
bool ExtractNodeCount(qihoo::ad::ConfigReader& conf_reader, int& count) {
  if (!conf_reader.getParameter(conf_section_nodes, conf_field_count, count)) {
    LOG(ERROR) << "node count not set!";
    return false;
  }

  return true;
}

// 提取node信息
// NODES : count
// NODE0 ：{ip, port}
bool ExtractNodeInfo(qihoo::ad::ConfigReader& conf_reader,
                     std::map<uint32_t, NodeInfo>& nodes) {
  int node_count = 0;
  if (!ExtractNodeCount(conf_reader, node_count)) {
    LOG(ERROR) << "extract node count failed!";
    return false;
  }

  char section_name[section_name_length] = {0};
  for (int i = 0; i < node_count; i++) {
    snprintf(section_name, section_name_length, "%s%d",
             conf_section_node.c_str(), i);
    std::string ip;
    if(!conf_reader.getParameter(section_name, conf_field_ip, ip)) {
      LOG(ERROR) << section_name << " ip not set!";
      return false;
    }
    int port;
    if(!conf_reader.getParameter(section_name, conf_field_port, port)) {
      LOG(ERROR) << section_name << " port not set!";
      return false;
    }
    nodes[i].ip = ip;
    nodes[i].port = port;
  }

  return true;
}

// 生成node配置信息
// 格式同上
void FormatNodeInfo(ConfigWriter& conf_writer,
                    const std::vector<NodeInfo>& nodes) {
  size_t node_count = nodes.size();
  conf_writer.SetParameter(conf_section_nodes, conf_field_count, node_count);

  std::vector<NodeInfo>::const_iterator it = nodes.begin();
  std::vector<NodeInfo>::const_iterator end = nodes.end();
  int node_index = 0;
  for (; it != end; ++ it) {
    std::stringstream node;
    node << conf_section_node << node_index++;
    conf_writer.SetParameter(node.str(), conf_field_ip, it->ip);
    conf_writer.SetParameter(node.str(), conf_field_port, it->port);

    std::vector<std::string>::const_iterator sit = it->storages.begin();
    std::vector<std::string>::const_iterator send = it->storages.end();
    std::stringstream storages;
    for (;;) {
      storages << *sit;
      if (++sit == send) {
        break;
      }
      storages << level0_delim;
    }

    std::string str_storages(storages.str());
    conf_writer.SetParameter(node.str(), conf_field_storage, str_storages);
  }
}

// 提取partition数量
// PARTITIONS : count
bool ExtractPartitionCount(qihoo::ad::ConfigReader& conf_reader, int& count) {
  if (!conf_reader.getParameter(conf_section_partitions,
                                conf_field_count, count)) {
    LOG(ERROR) << "partition count not set!";
    return false;
  }

  return true;
}

// 提取partition信息
// PARTITIONS : count
// PARTITION0 : group
bool ExtractPartitionInfo(qihoo::ad::ConfigReader& conf_reader,
                          std::vector<uint32_t>& partition_group_map) {
  std::vector<uint32_t> tmp_partition_group_map;

  int partition_count = 0;
  if (!ExtractPartitionCount(conf_reader, partition_count)) {
    LOG(ERROR) << "extract partition count failed!";
    return false;
  }

  tmp_partition_group_map.resize(partition_count);
  char section_name[section_name_length] = {0};
  for (int i = 0; i < partition_count; i++) {
    snprintf(section_name, section_name_length, "%s%d",
             conf_section_partition.c_str(), i);
    uint32_t group_id;
    if(!conf_reader.getParameter(section_name, conf_field_group, group_id)) {
      LOG(ERROR) << section_name << " group not set!";
      return false;
    }

    tmp_partition_group_map[i] = group_id;
  }

  partition_group_map.swap(tmp_partition_group_map);
  return true;
}

// 生成partition配置信息
// 格式同上
void FormatPartitionInfo(
    ConfigWriter& conf_writer,
    const std::vector<kvstore::util::PartitionInfo>& partitions) {
  size_t partition_count = partitions.size();
  conf_writer.SetParameter(conf_section_partitions,
                           conf_field_count,
                           partition_count);
  std::vector<kvstore::util::PartitionInfo>::const_iterator it =
      partitions.begin();
  std::vector<kvstore::util::PartitionInfo>::const_iterator end =
      partitions.end();
  int partition_index = 0;
  for (; it != end; ++ it) {
    std::stringstream partition;
    partition << conf_section_partition << partition_index++;
    conf_writer.SetParameter(partition.str(),
                             conf_field_group,
                             it->group_belong);

    std::vector<std::pair<int, int> >::const_iterator sit =
        it->destinations.begin();
    std::vector<std::pair<int, int> >::const_iterator send =
        it->destinations.end();
    std::stringstream destinations;
    for (;;) {
      destinations << sit->first << level1_delim << sit->second;
      if (++sit == send) {
        break;
      }
      destinations << level0_delim;
    }

    std::string str_destinations(destinations.str());
    conf_writer.SetParameter(partition.str(),
                             conf_field_storages,
                             str_destinations);
  }
}

// 提取client信息
// CLIENT ：{conn_timeout, recv_timeout, send_timeout, max_retries}
bool ExtractClientInfo(qihoo::ad::ConfigReader& conf_reader,
                       ClientInfo& client_info, bool strict/* = false*/) {
  if (!conf_reader.getParameter(conf_section_client,
                                conf_field_conn_timeout,
                                client_info.conn_timeout)) {
    if (strict) {
      LOG(ERROR) << "conn timeout not set!";
      return false;
    }
    client_info.conn_timeout = default_conn_timeout;
    LOG(WARNING) << "conn timeout not set!use default(15ms) instead.";
  }

  if (!conf_reader.getParameter(conf_section_client,
                                conf_field_recv_timeout,
                                client_info.recv_timeout)) {
    if (strict) {
      LOG(ERROR) << "recv timeout not set!";
      return false;
    }
    client_info.recv_timeout = default_recv_timeout;
    LOG(WARNING) << "recv timeout not set!use default(10ms) instead.";
  }

  if (!conf_reader.getParameter(conf_section_client,
                                conf_field_send_timeout,
                                client_info.send_timeout)) {
    if (strict) {
      LOG(ERROR) << "send timeout not set!";
      return false;
    }
    client_info.send_timeout = default_send_timeout;
    LOG(WARNING) << "send timeout not set!use default(5ms) instead.";
  }

  if (!conf_reader.getParameter(conf_section_client,
                                conf_field_max_retries,
                                client_info.max_retries)) {
    if (strict) {
      LOG(ERROR) << "max retries not set!";
      return false;
    }
    client_info.max_retries = default_max_retries;
    LOG(WARNING) << "max retries not set!use default(3) instead.";
  }

  return true;
}

// 生成client配置信息
// 格式同上
void FormatClientInfo(ConfigWriter& conf_writer,
                      const kvstore::util::ClientInfo& client_info) {
  conf_writer.SetParameter(conf_section_client,
                           conf_field_conn_timeout,
                           client_info.conn_timeout);
  conf_writer.SetParameter(conf_section_client,
                           conf_field_recv_timeout,
                           client_info.recv_timeout);
  conf_writer.SetParameter(conf_section_client,
                           conf_field_send_timeout,
                           client_info.send_timeout);
  conf_writer.SetParameter(conf_section_client,
                           conf_field_max_retries,
                           client_info.max_retries);
}

// 提取server信息
// SERVER ：{ip, port}
bool ExtractServerInfo(qihoo::ad::ConfigReader& conf_reader,
                       NodeInfo& server_info, bool strict/* = false*/) {
  if(!conf_reader.getParameter(conf_section_server,
                               conf_field_ip, server_info.ip)) {
    if (strict) {
      LOG(ERROR) << "server ip not set!";
      return false;
    }

    server_info.ip = default_server_ip;
    LOG(WARNING) << "server ip not found!use default(127.0.0.1) instead.\n";
  }

  if(!conf_reader.getParameter(conf_section_server,
                               conf_field_port, server_info.port)) {
    if (strict) {
      LOG(ERROR) << "server port not set!";
      return false;
    }

    server_info.port = default_server_port;
    LOG(WARNING) << "server port not found!use default(8090) instead.\n";
  }

  return true;
}

// 提取日志信息
// LOG ：{dir, level}
bool ExtractLogInfo(qihoo::ad::ConfigReader& conf_reader,
                    LogInfo& log_info, bool strict/* = false*/) {
  if(!conf_reader.getParameter(conf_section_log,
                               conf_field_dir, log_info.dir)) {
    if (strict) {
      LOG(ERROR) << "log dir not set!";
      return false;
    }

    log_info.dir = default_log_dir;
    LOG(WARNING) << "log dir not found!use default(log/) instead.\n";
  }

  if(!conf_reader.getParameter(conf_section_log,
                               conf_field_level, log_info.level)) {
    if (strict) {
      LOG(ERROR) << "log level not set!";
      return false;
    }

    log_info.level = google::ERROR;
    LOG(WARNING) << "log level not found!use default(ERROR) instead.\n";
  }

  return true;
}

// 提取table配置路径
// TABLE ：{conf_path}
bool ExtractTableConfPath(qihoo::ad::ConfigReader& conf_reader,
                          std::string& conf_path, bool strict/* = false*/) {
  if(!conf_reader.getParameter(conf_section_table,
                               conf_field_conf, conf_path)) {
    if (strict) {
      LOG(ERROR) << "table conf path not set!";
      return false;
    }

    conf_path = default_table_conf;
    LOG(WARNING) << "table conf path not found!use default instead.\n";
  }

  return true;
}

// 提取storage area信息
// STORAGES : count
// STORAGE0 : path
bool ExtractStorageAreaList(qihoo::ad::ConfigReader& conf_reader,
                            std::vector<std::string>& storage_area_list) {
  std::vector<std::string> tmp_storage_area_list;

  int storage_count = 0;
  if(!conf_reader.getParameter(conf_section_storages,
                               conf_field_count, storage_count)) {
    LOG(ERROR) << "storage count not set!";
    return false;
  }
  char section_name[section_name_length] = {0};
  for (int i = 0; i < storage_count; i++) {
    snprintf(section_name, section_name_length, "%s%d",
             conf_section_storage.c_str(), i);

    std::string path;
    if(!conf_reader.getParameter(section_name, conf_field_path, path)) {
      LOG(ERROR) << section_name << " path not set!";
      return false;
    }

    tmp_storage_area_list.push_back(path);
  }

  storage_area_list.swap(tmp_storage_area_list);
  return true;
}

// 提取storage area信息
// TABLES : count
// TABLE0 : name
bool ExtractTableNameList(qihoo::ad::ConfigReader& conf_reader,
                          std::vector<std::string>& table_name_list) {
  std::vector<std::string> tmp_table_name_list;

  int table_count = 0;
  if(!conf_reader.getParameter(conf_section_tables,
                               conf_field_count, table_count)) {
    LOG(ERROR) << "table count not set!";
    return false;
  }
  char section_name[section_name_length] = {0};
  for (int i = 0; i < table_count; i++) {
    sprintf(section_name, "%s%d", conf_section_table.c_str(), i);

    std::string name;
    if(!conf_reader.getParameter(section_name, conf_field_name, name)) {
      LOG(ERROR) << section_name << " name not set!";
      return false;
    }

    tmp_table_name_list.push_back(name);
  }

  table_name_list.swap(tmp_table_name_list);
  return true;
}

}
}
