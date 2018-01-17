#ifndef __BASE_64_H__
#include <string>

std::string base64_encode(char const* , unsigned int len);
void base64_decode(std::string const& s, std::string& d);

#endif
