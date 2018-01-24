#!/bin/env python

# FastTrie 2.3.8 2012-03-28

# NOTE: This python program mixes with C++ code. It's recommended adding
#       following lines (without the #) in your .vimrc for better reading:
#
# au BufReadPost *.py unlet b:current_syntax
# au BufReadPost *.py syntax include @Cpp syntax/cpp.vim
# au BufReadPost *.py syntax region CppRegion keepend contains=@Cpp
#     \ start=+"" """+ end=+""" ""+

import sys, optparse, re, os, tempfile, shutil, signal, md5

if sys.version_info >= (2, 4):
	import subprocess
else:
	import popen2

# parse command line

parser = optparse.OptionParser(
		usage = "\n  %prog [options] < input.txt > output.ft"
						"\n  %prog [options] input.ft .. > output.txt")
parser.add_option("-f", "--format", default = r'T(c*)\n',
		help = "specify container format string (default: '%default')")
parser.add_option("-d", "--disk",  action = "store_true", default = False,
		help = "swap intermediate data on disk during building (default: in memory)")
parser.add_option("-p", "--print", action = "store_true", default = False,
		help = "print Trie values by manually inputing keys", dest = "printing")
parser.add_option("-I", "--include", metavar = "DIR",
		help = "specify the path to FastTrie.h and MMap.h")
parser.add_option("-x", "--extend", metavar = "FILE", action = "append", default = [],
		help = "include some C/C++ source file for use in HashMap")
parser.add_option("-c", "--compile", metavar = "DIR",
		help = "generate and compile C++ source code in DIR")

(options, args) = parser.parse_args()

# parse container format string

class Container:
	pttnType      = r'(?:[cCbBsSlLqQfdu])'             # type (e.g. char, uint32_t)
	pttnSeparator = r'(?:[^*()\\]|\\x..|\\.)'          # type separator (e.g. '\na123:\n')
	pttnWeakerSep = r'(?:[^0-9A-Za-z*()\\]|\\x..|\\.)' # weaker type separator (e.g. '\t')
	pttnTarg      = r'(?:(?:,[^,()]+)+)'               # template arguments (e.g. FT_TAIL)

	# match a struct or struct sequence
	pttnTypeSeq   = r'(?P<pre>' + pttnWeakerSep + r'*)' \
			+ r'(?P<seq>(?:' + pttnType + pttnWeakerSep + r'*)+)\*?'
	# match a Vector
	pttnVector    = r'V(?P<arg>(?:' + pttnTarg + r')?)' \
			+ r'\((?P<sub>.+)\)(?P<sep>' + pttnSeparator + r'+)'
	# match a Trie<bool>
	pttnTrieSet   = r'T(?P<arg>(?:' + pttnTarg + r')?)' \
			+ r'\((?P<key>' + pttnTypeSeq + r')\)(?P<keysep>' + pttnSeparator + r'+)'
	# match a Trie
	pttnTrie      = r'T(?P<arg>(?:' + pttnTarg + r')?)' \
			+ r'\((?P<key>' + pttnTypeSeq + r')\)(?P<keysep>' + pttnSeparator + r'+)' \
			+ r'\((?P<sub>.+)\)(?P<sep>' + pttnSeparator + r'+)'
	# match a HashMap<bool>
	pttnHashSet   = r'H(?P<arg>(?:' + pttnTarg + r')?)' \
			+ r'\((?P<key>' + pttnTypeSeq + r')\)(?P<keysep>' + pttnSeparator + r'+)'
	# match a HashMap
	pttnHashMap   = r'H(?P<arg>(?:' + pttnTarg + r')?)' \
			+ r'\((?P<key>' + pttnTypeSeq + r')\)(?P<keysep>' + pttnSeparator + r'+)' \
			+ r'\((?P<sub>.+)\)(?P<sep>' + pttnSeparator + r'+)'

	type2codes = {
			"c": "char",    "C": "unsigned char",
			"b": "int8_t",  "B": "uint8_t",
			"s": "int16_t", "S": "uint16_t",
			"l": "int32_t", "L": "uint32_t",
			"q": "int64_t", "Q": "uint64_t",
			"f": "float",   "d": "double",   "u": "uint16_t",
	}

	# generate containers recursively
	# self.type: C++ type of the container, e.g. Trie<Vector<Struct_2 > >
	# self.code: C++ code for reading or writing the C++ type above
	# self.size: How many sub containers
	def __init__(self, n, format):
		if re.match(self.pttnTypeSeq + '$', format):
			self.m = re.match(self.pttnTypeSeq + '$', format)

			if self.m.group("pre") + self.m.group("seq") == format:
				# a struct
				self.type = "Struct_" + str(n) + " "
				self.code = self.format2Struct(n) \
						+ self.format2getStruct(n) + self.format2putStruct(n) \
						+ self.format2buildStruct(n)
				self.size = 1
			else:
				# a struct sequence
				self.type = "Vector<Struct_" + str(n) + " > "
				self.code = self.format2Struct(n) \
						+ self.format2getVectorStruct(n) + self.format2putVectorStruct(n) \
						+ self.format2buildVectorStruct(n)
				self.size = 1
		elif re.match(self.pttnVector + '$', format):
			self.m = re.match(self.pttnVector + '$', format)

			self.sub = Container(n + 1, self.m.group("sub"))

			# a Vector
			self.type = "Vector<" + self.sub.type + self.m.group("arg") + " > "
			self.fake = "Vector<bool"             + self.m.group("arg") + " > "
			self.code = self.sub.code \
					+ self.format2getVector(n) + self.format2putVector(n) \
					+ self.format2buildVector(n)
			self.size = self.sub.size + 1
		elif re.match(self.pttnTrieSet + '$', format):
			self.m = re.match(self.pttnTrieSet + '$', format)

			self.key = Container(n + 1, self.m.group("key"))

			# a Trie<bool>
			self.type = "Trie<bool" + self.m.group("arg") + " > "
			self.code = self.key.code \
					+ self.format2getTrieSet(n) + self.format2putTrieSet(n) \
					+ self.format2buildTrieSet(n)
			self.size = self.key.size + 1
		elif re.match(self.pttnTrie + '$', format):
			self.m = re.match(self.pttnTrie + '$', format)

			self.key = Container(n + 1, self.m.group("key"))
			self.sub = Container(n + 2, self.m.group("sub"))

			# a Trie
			self.type = "Trie<"  + self.sub.type + self.m.group("arg") + " > "
			self.fake = "Trie<fstream::pos_type" + self.m.group("arg") + " > "
			self.code = self.key.code + self.sub.code \
					+ self.format2getTrie(n) + self.format2putTrie(n) \
					+ self.format2buildTrie(n)
			self.size = self.key.size + self.sub.size + 1
		elif re.match(self.pttnHashSet + '$', format):
			self.m = re.match(self.pttnHashSet + '$', format)

			self.key = Container(n + 1, self.m.group("key"))

			# a HashMap<bool>
			self.type = "HashMap<" + self.key.type \
					+ ", bool" + self.m.group("arg") + " > "
			self.code = self.key.code \
					+ self.format2getTrieSet(n) + self.format2putTrieSet(n) \
					+ self.format2buildTrieSet(n) # just use Trie's code
			self.size = self.key.size + 1
		elif re.match(self.pttnHashMap + '$', format):
			self.m = re.match(self.pttnHashMap + '$', format)

			self.key = Container(n + 1, self.m.group("key"))
			self.sub = Container(n + 2, self.m.group("sub"))

			# a HashMap
			self.type = "HashMap<" + self.key.type \
					+ ", "  + self.sub.type + self.m.group("arg") + " > "
			self.fake = "HashMap<" + self.key.type \
					+ ", fstream::pos_type" + self.m.group("arg") + " > "
			self.code = self.key.code + self.sub.code \
					+ self.format2getTrie(n) + self.format2putTrie(n) \
					+ self.format2buildTrie(n) # just use Trie's code
			self.size = self.key.size + self.sub.size + 1
		else:
			for m in re.finditer(r'(?P<sep>' + self.pttnSeparator + r'+)', format):
				try:
					if m.start() < 4 or m.end() > len(format) - 3: continue

					self.sub1 = Container(n + 1,                  format[2:m.start() - 1])
					self.sub2 = Container(n + 1 + self.sub1.size, format[m.end() + 1:- 1])

					# match a Pair
					pttnPair = r'P' \
							+ r'\((?P<sub1>' + re.escape(self.sub1.m.group(0)) + r')\)' \
							+ r'(?P<sep>' + self.pttnSeparator + r'+)' \
							+ r'\((?P<sub2>' + re.escape(self.sub2.m.group(0)) + r')\)'

					self.m = re.match(pttnPair + '$', format)
				except:
					continue
				break
			else:
				raise ValueError("incorrect format string '" + format + "'")

			# a Pair
			self.type = "Pair<" + self.sub1.type + ", " + self.sub2.type + "> "
			self.code = self.sub1.code + self.sub2.code \
					+ self.format2getPair(n) + self.format2putPair(n) \
					+ self.format2buildPair(n)
			self.size = self.sub1.size + self.sub2.size + 1

	# generate struct
	def format2Struct(self, n):
		matches = map(lambda x: x, re.finditer(
				'(' + self.pttnType + ')(' + self.pttnWeakerSep + '*)', self.m.group("seq")))

		if len(matches) == 1:
			return "typedef " \
					+ self.type2codes[matches[0].group(1)] + " Struct_" + str(n) + ";\n\n"

		code = "struct Struct_" + str(n) + "\n{\n"

		for v in range(len(matches)):
			type = matches[v].group(1)

			code += "\t" + self.type2codes[type] + " v" + str(v) + ";\n"

		# need operator < to use Struct as key in std::map
		code += "\n\tbool operator <(const Struct_" + str(n) + " &x) const\n\t{\n"

		for v in range(len(matches)):
			code += "\t\tif (v" + str(v) + " < x.v" + str(v) + ") return true;\n"
			code += "\t\tif (v" + str(v) + " > x.v" + str(v) + ") return false;\n"

		code += "\n\t\treturn false;\n\t}\n};\n\n"

		return code

	# generate function for building a struct container
	def format2buildStruct(self, n):
		return "" """\
int build_""" + str(n) + """(istream &in, const string &separator = "")
{
	string line;

	typedef Container<""" + self.type + """>::std_value_type std_type;

	if (separator.empty() && """\
			+ (self.m.group(0).lower() == "c" and "true" or "false") + """)
	{
		string values((istreambuf_iterator<char>(in)), istreambuf_iterator<char>());

		Container<""" + self.type + """>::build(ostreambuf_iterator<char>(cout),
				(std_type *)&*values.begin(), (std_type *)&*values.end());
	}
	else
	{
		vector<std_type> values;
		std_type v;

		if (separator.empty())
			while (get_""" + str(n) + """(in, v) == 0)
				values.push_back(v);
		else
			while (getline(in, line, separator))
			{
				istringstream isv(line);
				if (get_""" + str(n) + """(isv, v) == 0)
					values.push_back(v);
			}

		Container<""" + self.type + """>::build(ostreambuf_iterator<char>(cout),
				&*values.begin(), &*values.end());
	}

	return 0;
}

""" ""

	# generate function for reading a struct
	def format2getStruct(self, n):
		matches = map(lambda x: x, re.finditer(
				'(' + self.pttnType + ')(' + self.pttnWeakerSep + '*)', self.m.group("seq")))

		code = "int get_" + str(n) \
				+ "(istream &in, Container<" + self.type + ">::std_value_type &x)\n{\n"

		code += "\tmemset(&x, 0, sizeof(x));\n"

		if self.m.group("pre"):
			code += "\tskip(in, \"" + self.m.group("pre") + "\");\n"

		for v in range(len(matches)):
			type = matches[v].group(1)
			stop = matches[v].group(2)
			name = len(matches) > 1 and "x.v" + str(v) or "x"

			# read int8_t/uint8_t as int instead of char
			if   type == "b":
				code += "\t{  int32_t b; if (!(in >> b)) return -1; " + name + " = b; }\n"
			elif type == "B":
				code += "\t{ uint32_t B; if (!(in >> B)) return -1; " + name + " = B; }\n"
			# read signed/unsigned char using get()
			elif type == "c" or type == "C":
				code += "\t{ " + name + " = in.get(); if (!in) return -1; }\n"
			# read UTF-16 as UTF-8 chars
			elif type == "u":
				code += "\tif (!getUtf16(in, " + name + ")) return -1;\n"
			# read other types using iostream
			else:
				code += "\tif (!(in >> " + name + ")) return -1;\n"
			if stop:
				code += "\tskip(in, \"" + stop + "\");\n"

		code += "\n\treturn 0;\n}\n\n"

		return code

	# generate function for writing a struct
	def format2putStruct(self, n):
		matches = map(lambda x: x, re.finditer(
				'(' + self.pttnType + ')(' + self.pttnWeakerSep + '*)', self.m.group("seq")))

		code = "void put_" + str(n) \
				+ "(ostream &out, const " + self.type + " &x)\n{\n"

		if self.m.group("pre"):
			code += "\tout << \"" + self.m.group("pre") + "\";\n"

		for v in range(len(matches)):
			type = matches[v].group(1)
			stop = matches[v].group(2)
			name = len(matches) > 1 and "x.v" + str(v) or "x"

			# set proper floating point precision
			if   type == "f": code += "\tout.precision(numeric_limits<float >::digits10+2);\n"
			elif type == "d": code += "\tout.precision(numeric_limits<double>::digits10+2);\n"
			# write int8_t/uint8_t as int instead of char
			if   type == "b": code += "\tout << ( int32_t)" + name + ";\n"
			elif type == "B": code += "\tout << (uint32_t)" + name + ";\n"
			# write UTF-16 as UTF-8 chars
			elif type == "u": code += "\tputUtf16(out, " + name + ");\n"
			# write other types using iostream
			else:             code += "\tout << " + name + ";\n"
			if stop:          code += "\tout << \"" + stop + "\";\n"

		code += "}\n\n"

		return code

	# generate function for building a struct sequence container
	def format2buildVectorStruct(self, n):
		return "" """\
int build_""" + str(n) + """(istream &in, const string &separator = "")
{
	string line;

	typedef Container<""" + self.type + """>::std_value_type std_type;

	vector<uint32_t> entries(1);

	if (separator.empty() && """\
			+ (self.m.group(0).lower() == "c*" and "true" or "false") + """)
	{
		string values((istreambuf_iterator<char>(in)), istreambuf_iterator<char>());
		entries.push_back(values.size());

		Container<uint32_t>::build(ostreambuf_iterator<char>(cout),
				&*entries.begin(), &*entries.end());
		Container<std_type::value_type>::build(
				ostreambuf_iterator<char>(cout),
				(std_type::value_type *)&*values.begin(),
				(std_type::value_type *)&*values.end());
	}
	else
	{
		std_type values, v;

		if (separator.empty())
		{
			get_""" + str(n) + """(in, values);
			entries.push_back(values.size());
		}
		else
			while (getline(in, line, separator))
			{
""" + (self.m.group(0).lower() == "c*" and " " or """\
				istringstream isv(line);
				if (get_""" + str(n) + """(isv, v)) continue;
""") + """\

""" + (self.m.group(0).lower() == "c*" and """\
				values.insert(values.end(),
						(std_type::value_type *)&line[0],
						(std_type::value_type *)&line[line.size()]);
""" or """\
				values.insert(values.end(), v.begin(), v.end());
""") + """\
				entries.push_back(values.size());
			}

		Container<uint32_t>::build(ostreambuf_iterator<char>(cout),
				&*entries.begin(), &*entries.end());
		Container<std_type::value_type>::build(
				ostreambuf_iterator<char>(cout), &*values.begin(), &*values.end());
	}

	return 0;
}

""" ""

	# generate function for reading a struct sequence
	def format2getVectorStruct(self, n):
		matches = map(lambda x: x, re.finditer(
				'(' + self.pttnType + ')(' + self.pttnWeakerSep + '*)', self.m.group("seq")))

		code = "int get_" + str(n) \
				+ "(istream &in, Container<" + self.type + ">::std_value_type &x)\n{\n"

		code += "\tContainer<" + self.type + ">::std_value_type::value_type v;\n"
		code += "\tmemset(&v, 0, sizeof(v));\n"
		code += "\tx.resize(0);\n\n"
		code += "\twhile (in)\n\t{\n"

		if self.m.group("pre"):
			code += "\t\tskip(in, \"" + self.m.group("pre") + "\");\n"

		for v in range(len(matches)):
			type = matches[v].group(1)
			stop = matches[v].group(2)
			name = len(matches) > 1 and "v.v" + str(v) or "v"

			# read int8_t/uint8_t as int instead of char
			if   type == "b":
				code += "\t\t{  int32_t b; if (!(in >> b)) continue; " + name + " = b; }\n"
			elif type == "B":
				code += "\t\t{ uint32_t B; if (!(in >> B)) continue; " + name + " = B; }\n"
			# read signed/unsigned char using get()
			elif type == "c" or type == "C":
				code += "\t\t{ " + name + " = in.get(); if (!in) continue; }\n"
			# read UTF-16 as UTF-8 chars
			elif type == "u":
				code += "\t\tif (!getUtf16(in, " + name + ")) continue;\n"
			# read other types using iostream
			else:
				code += "\t\tif (!(in >> " + name + ")) continue;\n"
			if stop:
				code += "\t\tskip(in, \"" + stop + "\");\n"

		code += "\n\t\tx.push_back(v);\n"
		code += "\t}\n\n"
		code += "\treturn 0;\n}\n\n"

		return code

	# generate function for writing a struct sequence
	def format2putVectorStruct(self, n):
		matches = map(lambda x: x, re.finditer(
				'(' + self.pttnType + ')(' + self.pttnWeakerSep + '*)', self.m.group("seq")))

		code  = "template <class ContainerT>\n"
		code += "void put_" + str(n) + "(ostream &out, const ContainerT &x)\n{\n"

		code += "\tfor (size_t i = 0; i != x.size(); i ++)\n\t{\n"

		if self.m.group("pre"):
			code += "\t\tout << \"" + self.m.group("pre") + "\";\n"

		for v in range(len(matches)):
			type = matches[v].group(1)
			stop = matches[v].group(2)
			name = len(matches) > 1 and "x[i].v" + str(v) or "x[i]"

			# set proper floating point precision
			if   type == "f": code += "\t\tout.precision(numeric_limits<float >::digits10 + 2);\n"
			elif type == "d": code += "\t\tout.precision(numeric_limits<double>::digits10 + 2);\n"
			# write int8_t/uint8_t as int instead of char
			if   type == "b": code += "\t\tout << ( int32_t)" + name + ";\n"
			elif type == "B": code += "\t\tout << (uint32_t)" + name + ";\n"
			# write UTF-16 as UTF-8 chars
			elif type == "u": code += "\t\tputUtf16(out, " + name + ");\n"
			# write other types using iostream
			else:             code += "\t\tout << " + name + ";\n"
			if stop:          code += "\t\tout << \"" + stop + "\";\n"

		code += "\t}\n}\n\n"

		return code

	# generate function for building a Vector container
	def format2buildVector(self, n):
		return "" """\
int build_""" + str(n) + """(istream &in, const string &separator = "")
{
	string line;

	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	typedef Container<""" + self.type + """>::std_value_type std_type;
	typedef Container<""" + self.fake + """>::std_value_type fake_type;

	vector<fake_type> fake_values;

	fstream tmp((tmpdir + """ + '\"/' + str(n) + '\"' + """).c_str(),
			ios::in | ios::out | ios::trunc);

	if (separator.empty())
	{
		std_type::value_type v;

		fake_values.push_back(fake_type());
		while (getline(in, line, sep))
		{
""" + (self.m.group("sub").lower() == "c*" and " " or """\
			istringstream isv(line);
			if (get_""" + str(n + 1) + """(isv, v)) continue;
""") + """\

			fake_values.back().push_back(fake_type::value_type());
""" + (self.m.group("sub").lower() == "c*" and """\
			tmp << line << sep;
""" or """\
			put_""" + str(n + 1) + """(tmp, v); tmp << sep;
""") + """\
		}
	}
	else
		while (getline(in, line, separator))
		{
			size_t size = 0;
			for (size_t i = line.find(sep); i != string::npos;
					i = line.find(sep, i + sep.size())) size ++;
			fake_values.push_back(fake_type(size));
			tmp << line;
		}

	Container<""" + self.fake + """>::build(ostreambuf_iterator<char>(cout),
			fake_values.begin(), fake_values.end(), (void *)(-1));
	fake_values.clear();

	tmp.seekg(0, ios::beg);
	build_""" + str(n + 1) + """(tmp, sep);

	tmp.close();
	unlink((tmpdir + """ + '\"/' + str(n) + '\"' + """).c_str());

	return 0;
}

""" ""

	# generate function for reading a Vector
	def format2getVector(self, n):
		return "" """\
int get_""" + str(n) + """(
		istream &in, Container<""" + self.type + """>::std_value_type &x)
{
	string line;

	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	typedef Container<""" + self.sub.type + """>::std_value_type value_type;
	Container<""" + self.sub.type + """>::std_value_type v;
	x.resize(0);

	while (getline(in, line, sep))
	{
""" + (self.m.group("sub").lower() == "c*" and " " or """\
		istringstream isv(line);
		if (get_""" + str(n + 1) + """(isv, v)) continue;
""") + """\

""" + (self.m.group("sub").lower() == "c*" and """\
		x.push_back(value_type(
				(value_type::value_type *)&line[0],
				(value_type::value_type *)&line[line.size()]));
""" or """\
		x.push_back(v);
""") + """\
	}

	return 0;
}

""" ""

	# generate function for writing a Vector
	def format2putVector(self, n):
		return "" """\
template <class ContainerT>
void put_""" + str(n) + """(ostream &out, const ContainerT &x)
{
	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	for (size_t i = 0; i != x.size(); i ++)
	{
""" + (self.m.group("sub").lower() == "c*" and """\
		out << string((char *)&*x[i].begin(), (char *)&*x[i].end());
""" or """\
		put_""" + str(n + 1) + """(out, x[i]);
""") + """\
		out << sep;
	}
}

""" ""

	# generate function for building a Trie<bool> container
	def format2buildTrieSet(self, n):
		return "" """\
int build_""" + str(n) + """(istream &in, const string &separator = "")
{
	string line;

	typedef Container<""" + self.type + """>::std_value_type std_type;

	vector<std_type> values;
	std_type v;

	if (separator.empty())
	{
		values.push_back(std_type());
		get_""" + str(n) + """(in, values.back());
	}
	else
		while (getline(in, line, separator))
		{
			istringstream isv(line);
			if (get_""" + str(n) + """(isv, v)) continue;

			values.push_back(v);
		}

	Container<""" + self.type + """>::build(ostreambuf_iterator<char>(cout),
			values.begin(), values.end());

	return 0;
}

""" ""

	# generate function for reading a Trie<bool>
	def format2getTrieSet(self, n):
		return "" """\
int get_""" + str(n) + """(
		istream &in, Container<""" + self.type + """>::std_value_type &x)
{
	string line;

	static const string keysep = """ + '\"' + self.m.group("keysep") + '\"' + """;

""" + ((self.type[0] == 'T' or self.m.group("key").lower() == "c*") and """\
	typedef Container<""" + self.type + """>::std_value_type
			::value_type::first_type::value_type char_type;
""" or " ") + """\
	Container<""" + self.key.type + """>::std_value_type k;
	x.clear();

	while (getline(in, line, keysep))
	{
""" + (self.m.group("key").lower() == "c*" and " " or """\
		istringstream isk(line);
		if (get_""" + str(n + 1) + """(isk, k)) continue;
""") + """\

""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
		x[vector<char_type>((char_type *)&line[0], (char_type *)&line[line.size()])] = true;
""" or (self.key.type[0] == 'V' and """\
		x[vector<char_type>((char_type *)&k[0], (char_type *)&k[k.size()])] = true;
""" or """\
		x[vector<char_type>((char_type *)(&k), (char_type *)(&k + 1))] = true;
""")) + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
		x[vector<char_type>((char_type *)&line[0], (char_type *)&line[line.size()])] = true;
""" or """\
		x[k] = true;
""") + """\
""") + """\
	}

	return 0;
}

""" ""

	# generate function for writing a Trie<bool>
	def format2putTrieSet(self, n):
		return "" """\
template <class ContainerT>
void put_""" + str(n) + """(ostream &out, const ContainerT &x)
{
	static const string keysep = """ + '\"' + self.m.group("keysep") + '\"' + """;

	for (size_t i = 0; i != x.size(); i ++)
	{
""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << x.template key<string>(x.begin() + i);
""" or """\
		put_""" + str(n + 1) + """(out, x.template key<Container<
				""" + self.key.type + """>::std_value_type>(x.begin() + i));
""") + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << string(
				(char *)(x.begin() + i)->first.begin(),
				(char *)(x.begin() + i)->first.end());
""" or """\
		put_""" + str(n + 1) + """(out, (x.begin() + i)->first);
""") + """\
""") + """\
		out << keysep;
	}
}

template <class _Key, class _Tp, class _Compare, class _Alloc>
void put_""" + str(n) + """(
		ostream &out, const map<_Key, _Tp, _Compare, _Alloc> &x)
{
	static const string keysep = """ + '\"' + self.m.group("keysep") + '\"' + """;

	typedef Container<""" + self.key.type + """>::std_value_type key_type;

	for (typename map<_Key, _Tp, _Compare, _Alloc>::const_iterator
			it = x.begin(); it != x.end(); ++ it)
	{
""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << string((char *)&*it->first.begin(), (char *)&*it->first.end());
""" or (self.key.type[0] == 'V' and """\
		put_""" + str(n + 1) + """(out, key_type(
				(key_type::value_type *)&*it->first.begin(),
				(key_type::value_type *)&*it->first.end()));
""" or """\
		put_""" + str(n + 1) + """(out, *(key_type *)&*it->first.begin());
""")) + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << string((char *)&*it->first.begin(), (char *)&*it->first.end());
""" or """\
		put_""" + str(n + 1) + """(out, it->first);
""") + """\
""") + """\
		out << keysep;
	}
}

""" ""

	# generate function for building a Trie container
	def format2buildTrie(self, n):
		return "" """\
int build_""" + str(n) + """(istream &in, const string &separator = "")
{
	string line;

	static const string keysep = """ + '\"' + self.m.group("keysep") + '\"' + """;
	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	typedef Container<""" + self.type + """>::std_value_type std_type;
	typedef Container<""" + self.fake + """>::std_value_type fake_type;
	typedef Container<""" + self.key.type + """>::std_value_type std_key_type;
""" + ((self.type[0] == 'T' or self.m.group("key").lower() == "c*") and """\
	typedef std_type::value_type::first_type::value_type char_type;
""" or " ") + """\

	vector<fake_type> fake_values;
	std_key_type k;
	std_type::value_type::second_type v;

	fstream tmp((tmpdir + """ + '\"/' + str(n) + '-p\"' + """).c_str(),
			ios::in | ios::out | ios::trunc);
	fstream tmg((tmpdir + """ + '\"/' + str(n) + '-g\"' + """).c_str(),
			ios::in | ios::out | ios::trunc);

	if (separator.empty())
	{
		fake_values.push_back(fake_type());
		while (getline(in, line, sep))
		{
			size_t t = line.find(keysep);
			if (t == string::npos) continue;

""" + (self.m.group("key").lower() == "c*" and " " or """\
			istringstream isk(line.substr(0, t));
			if (get_""" + str(n + 1) + """(isk, k)) continue;
""") + """\

""" + (self.m.group("sub").lower() == "c*" and " " or """\
			istringstream isv(line.substr(t + keysep.size()));
			if (get_""" + str(n + 2) + """(isv, v)) continue;
""") + """\

""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
			fake_values.back()[vector<char_type>(
					(char_type *)&line[0], (char_type *)&line[t])] = tmp.tellp();
""" or (self.key.type[0] == 'V' and """\
			fake_values.back()[vector<char_type>(
					(char_type *)&k[0], (char_type *)&k[k.size()])] = tmp.tellp();
""" or """\
			fake_values.back()[vector<char_type>(
					(char_type *)(&k), (char_type *)(&k + 1))] = tmp.tellp();
""")) + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
			fake_values.back()[vector<char_type>(
					(char_type *)&line[0], (char_type *)&line[t])] = tmp.tellp();
""" or """\
			fake_values.back()[k] = tmp.tellp();
""") + """\
""") + """\

""" + (self.m.group("sub").lower() == "c*" and """\
			tmp << line.substr(t + keysep.size()) << sep;
""" or """\
			put_""" + str(n + 2) + """(tmp, v); tmp << sep;
""") + """\
		}
	}
	else
		while (getline(in, line, separator))
		{
			fake_values.push_back(fake_type());
			for (size_t s = 0, s_next; s < line.size(); s = s_next)
			{
				s_next = line.find(sep, s);
				if (s_next == string::npos) s_next = line.size();
				s_next += sep.size();

				size_t t = line.find(keysep, s);
				if (t == string::npos || t > s_next - sep.size()) continue;

""" + (self.m.group("key").lower() == "c*" and " " or """\
				istringstream isk(line.substr(s, t - s));
				if (get_""" + str(n + 1) + """(isk, k)) continue;
""") + """\

""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
				fake_values.back()[vector<char_type>(
						(char_type *)&line[s], (char_type *)&line[t])] = tmp.tellp();
""" or (self.key.type[0] == 'V' and """\
				fake_values.back()[vector<char_type>(
						(char_type *)&k[0], (char_type *)&k[k.size()])] = tmp.tellp();
""" or """\
				fake_values.back()[vector<char_type>(
						(char_type *)(&k), (char_type *)(&k + 1))] = tmp.tellp();
""")) + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
				fake_values.back()[vector<char_type>(
						(char_type *)&line[s], (char_type *)&line[t])] = tmp.tellp();
""" or """\
				fake_values.back()[k] = tmp.tellp();
""") + """\
""") + """\
				tmp << line.substr(t + keysep.size(),
						s_next - sep.size() - t - keysep.size()) << sep;
			}
		}

""" + (self.type[0] == 'T' and """\
	for (size_t i = 0; i != fake_values.size(); i ++)
		for (fake_type::const_iterator
				it = fake_values[i].begin(); it != fake_values[i].end(); ++ it)
		{
			tmp.seekg(it->second, ios::beg);
			getline(tmp, line, sep);
			tmg << line << sep;
		}

	Container<""" + self.fake + """>::build(ostreambuf_iterator<char>(cout),
			fake_values.begin(), fake_values.end(), (void *)(-1));
	fake_values.clear();
""" or """\
	size_t size = 0;
	for (size_t i = 0; i != fake_values.size(); i ++)
		size += fake_values[i].size();

	vector<fstream::pos_type> positions(size);

	Container<""" + self.fake + """>::build(ostreambuf_iterator<char>(cout),
			fake_values.begin(), fake_values.end(), &positions[0]);
	fake_values.clear();

	for (size_t i = 0; i != positions.size(); i ++)
	{
		tmp.seekg(positions[i], ios::beg);
		getline(tmp, line, sep);
		tmg << line << sep;
	}

	positions.clear();
""") + """\

	tmg.seekg(0, ios::beg);
	build_""" + str(n + 2) + """(tmg, sep);

	tmp.close();
	tmg.close();
	unlink((tmpdir + """ + '\"/' + str(n) + '-p\"' + """).c_str());
	unlink((tmpdir + """ + '\"/' + str(n) + '-g\"' + """).c_str());

	return 0;
}

""" ""

	# generate function for reading a Trie
	def format2getTrie(self, n):
		return "" """\
int get_""" + str(n) + """(
		istream &in, Container<""" + self.type + """>::std_value_type &x)
{
	string line;

	static const string keysep = """ + '\"' + self.m.group("keysep") + '\"' + """;
	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

""" + ((self.type[0] == 'T' or self.m.group("key").lower() == "c*") and """\
	typedef Container<""" + self.type + """>::std_value_type
			::value_type::first_type::value_type char_type;
""" or " ") + """\
	typedef Container<""" + self.sub.type + """>::std_value_type value_type;
	Container<""" + self.key.type + """>::std_value_type k;
	Container<""" + self.sub.type + """>::std_value_type v;
	x.clear();

	while (getline(in, line, sep))
	{
		size_t t = line.find(keysep);
		if (t == string::npos) continue;

""" + (self.m.group("key").lower() == "c*" and " " or """\
		istringstream isk(line.substr(0, t));
		if (get_""" + str(n + 1) + """(isk, k)) continue;
""") + """\

""" + (self.m.group("sub").lower() == "c*" and " " or """\
		istringstream isv(line.substr(t + keysep.size()));
		if (get_""" + str(n + 2) + """(isv, v)) continue;
""") + """\

""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
		x[vector<char_type>((char_type *)&line[0], (char_type *)&line[t])] =
""" or (self.key.type[0] == 'V' and """\
		x[vector<char_type>((char_type *)&k[0], (char_type *)&k[k.size()])] =
""" or """\
		x[vector<char_type>((char_type *)(&k), (char_type *)(&k + 1))] =
""")) + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
		x[vector<char_type>((char_type *)&line[0], (char_type *)&line[t])] =
""" or """\
		x[k] =
""") + """\
""") + """\

""" + (self.m.group("sub").lower() == "c*" and """\
				value_type(
					(value_type::value_type *)&line[t + keysep.size()],
					(value_type::value_type *)&line[line.size()]);
""" or """\
				v;
""") + """\
	}

	return 0;
}

""" ""

	# generate function for writing a Trie
	def format2putTrie(self, n):
		return "" """\
template <class ContainerT>
void put_""" + str(n) + """(ostream &out, const ContainerT &x)
{
	static const string keysep = """ + '\"' + self.m.group("keysep") + '\"' + """;
	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	for (size_t i = 0; i != x.size(); i ++)
	{
""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << x.template key<string>(x.begin() + i);
""" or """\
		put_""" + str(n + 1) + """(out, x.template key<Container<
				""" + self.key.type + """>::std_value_type>(x.begin() + i));
""") + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << string(
				(char *)(x.begin() + i)->first.begin(),
				(char *)(x.begin() + i)->first.end());
""" or """\
		put_""" + str(n + 1) + """(out, (x.begin() + i)->first);
""") + """\
""") + """\
		out << keysep;

""" + (self.type[0] == 'T' and """\
""" + (self.m.group("sub").lower() == "c*" and """\
		out << string(
				(char *)(x.begin() + i)->begin(), (char *)(x.begin() + i)->end());
""" or """\
		put_""" + str(n + 2) + """(out, *(x.begin() + i));
""") + """\
""" or """\
""" + (self.m.group("sub").lower() == "c*" and """\
		out << string(
				(char *)(x.begin() + i)->second.begin(),
				(char *)(x.begin() + i)->second.end());
""" or """\
		put_""" + str(n + 2) + """(out, (x.begin() + i)->second);
""") + """\
""") + """\
		out << sep;
	}
}

template <class _Key, class _Tp, class _Compare, class _Alloc>
void put_""" + str(n) + """(
		ostream &out, const map<_Key, _Tp, _Compare, _Alloc> &x)
{
	static const string keysep = """ + '\"' + self.m.group("keysep") + '\"' + """;
	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	typedef Container<""" + self.key.type + """>::std_value_type key_type;

	for (typename map<_Key, _Tp, _Compare, _Alloc>::const_iterator
			it = x.begin(); it != x.end(); ++ it)
	{
""" + (self.type[0] == 'T' and """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << string((char *)&*it->first.begin(), (char *)&*it->first.end());
""" or (self.key.type[0] == 'V' and """\
		put_""" + str(n + 1) + """(out, key_type(
				(key_type::value_type *)&*it->first.begin(),
				(key_type::value_type *)&*it->first.end()));
""" or """\
		put_""" + str(n + 1) + """(out, *(key_type *)&*it->first.begin());
""")) + """\
""" or """\
""" + (self.m.group("key").lower() == "c*" and """\
		out << string((char *)&*it->first.begin(), (char *)&*it->first.end());
""" or """\
		put_""" + str(n + 1) + """(out, it->first);
""") + """\
""") + """\
		out << keysep;

""" + (self.m.group("sub").lower() == "c*" and """\
		out << string((char *)&*it->second.begin(), (char *)&*it->second.end());
""" or """\
		put_""" + str(n + 2) + """(out, it->second);
""") + """\
		out << sep;
	}
}

""" ""

	# generate function for building a Pair container
	def format2buildPair(self, n):
		return "" """\
int build_""" + str(n) + """(istream &in, const string &separator = "")
{
	string line;

	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	typedef Container<""" + self.type + """>::std_value_type std_type;

	fstream tmp1((tmpdir + """ + '\"/' + str(n) + '-1\"' + """).c_str(),
			ios::in | ios::out | ios::trunc);
	fstream tmp2((tmpdir + """ + '\"/' + str(n) + '-2\"' + """).c_str(),
			ios::in | ios::out | ios::trunc);

	const string sep1 = separator.empty() ? "" : sep;
	const string sep2 = separator.empty() ? "" : separator;

	if (separator.empty())
	{
		string line((istreambuf_iterator<char>(in)), istreambuf_iterator<char>());

		size_t t = line.find(sep);
		if (t == string::npos) return -1;

		tmp1 << line.substr(0, t);
		tmp2 << line.substr(t + sep.size());
	}
	else
		while (getline(in, line, separator))
		{
			size_t t = line.find(sep);
			if (t == string::npos) return -1;

			tmp1 << line.substr(0, t);           tmp1 << sep1;
			tmp2 << line.substr(t + sep.size()); tmp2 << sep2;
		}

	tmp1.seekg(0, ios::beg);
	tmp2.seekg(0, ios::beg);
	build_""" + str(n + 1)                  + """(tmp1, sep1);
	build_""" + str(n + 1 + self.sub1.size) + """(tmp2, sep2);

	tmp1.close();
	tmp2.close();
	unlink((tmpdir + """ + '\"/' + str(n) + '-1\"' + """).c_str());
	unlink((tmpdir + """ + '\"/' + str(n) + '-2\"' + """).c_str());

	return 0;
}

""" ""

	# generate function for reading a Pair
	def format2getPair(self, n):
		return "" """\
int get_""" + str(n) + """(
		istream &in, Container<""" + self.type + """>::std_value_type &x)
{
	string line((istreambuf_iterator<char>(in)), istreambuf_iterator<char>());

	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

	typedef Container<""" + self.sub1.type + """>::std_value_type first_type;
	typedef Container<""" + self.sub2.type + """>::std_value_type second_type;

	size_t t = line.find(sep);
	if (t == string::npos) return -1;

""" + (self.m.group("sub1").lower() == "c*" and """\
	x.first = first_type(
			(first_type::value_type *)&line[0],
			(first_type::value_type *)&line[t]);
""" or """\
	istringstream isv1(line.substr(0, t));
	if (get_""" + str(n + 1) + """(isv1, x.first)) return -1;
""") + """\

""" + (self.m.group("sub2").lower() == "c*" and """\
	x.second = second_type(
			(second_type::value_type *)&line[t + sep.size()],
			(second_type::value_type *)&line[line.size()]);
""" or """\
	istringstream isv2(line.substr(t + sep.size()));
	if (get_""" + str(n + 1 + self.sub1.size) + """(isv2, x.second)) return -1;
""") + """\

	return 0;
}

""" ""

	# generate function for writing a Pair
	def format2putPair(self, n):
		return "" """\
template <class ContainerT>
void put_""" + str(n) + """(ostream &out, const ContainerT &x)
{
	static const string sep    = """ + '\"' + self.m.group("sep"   ) + '\"' + """;

""" + (self.m.group("sub1").lower() == "c*" and """\
	out << string((char *)&*x.first.begin(), (char *)&*x.first.end());
""" or """\
	put_""" + str(n + 1) + """(out, x.first);
""") + """\
	out << sep;

""" + (self.m.group("sub2").lower() == "c*" and """\
	out << string((char *)&*x.second.begin(), (char *)&*x.second.end());
""" or """\
	put_""" + str(n + 1 + self.sub1.size) + """(out, x.second);
""") + """\
}

""" ""

container = Container(0, options.format)

# generate C++ source code

cpp = "" """\
// generated by fasttrie.py -f '""" + options.format + """'

#include <iostream>
#include <fstream>
#include <sstream>
#include <limits>

#include "FastTrie.h"

""" + "\n".join(map(lambda x: '#include \"' + x + '\"', options.extend)) + """\

using namespace std;
using namespace ft2;

// common utility functions

const vector<string> split(const string &delimiter, const string &source)
{
	if (delimiter.empty()) return vector<string>(1, source);

	vector<string> result;

	size_t prev_pos = 0;
	size_t pos = source.find(delimiter, 0);
	while (pos != string::npos)
	{
		result.push_back(source.substr(prev_pos, pos - prev_pos));
		pos += delimiter.size();
		prev_pos = pos;
		pos = source.find(delimiter, pos);
	}
	result.push_back(source.substr(prev_pos));

	return result;
}

istream &getUtf16(istream &in, uint16_t &utf16)
{
	const uint16_t replacementChar = 0xFFFD;

	uint16_t result = (uint8_t)in.get(); if (!in) return in;

	if      (result < 0x80) ;
	else if (result < 0xC2) // unexpected continuation byte or overlong
		result = replacementChar;
	else if (result < 0xE0) // 2 bytes
	{
		result = (result & 0x1F) << 6;

		uint16_t next = (uint8_t)in.get(); if (!in) return in;
		if (next < 0x80 || next >= 0xC0) { utf16 = replacementChar; return in; }
		result |= (next & 0x3F);
	}
	else if (result < 0xF0) // 3 bytes
	{
		result = (result & 0xF) << 12;

		uint16_t next = (uint8_t)in.get(); if (!in) return in;
		if (next < 0x80 || next >= 0xC0) { utf16 = replacementChar; return in; }
		result |= (next & 0x3F) << 6;

		next          = (uint8_t)in.get(); if (!in) return in;
		if (next < 0x80 || next >= 0xC0) { utf16 = replacementChar; return in; }
		result |= (next & 0x3F);

		if (result < 0x800) result = replacementChar; // overlong
	}
	else if (result < 0xF8) // 4 bytes
	{
		uint16_t next = (uint8_t)in.get(); if (!in) return in;
		if (next < 0x80 || next >= 0xC0) { utf16 = replacementChar; return in; }
		next          = (uint8_t)in.get(); if (!in) return in;
		if (next < 0x80 || next >= 0xC0) { utf16 = replacementChar; return in; }
		next          = (uint8_t)in.get(); if (!in) return in;
		if (next < 0x80 || next >= 0xC0) { utf16 = replacementChar; return in; }

		result = replacementChar; // not in UCS-2
	}
	else
		result = replacementChar; // not in UTF-8 standard

	utf16 = result; return in;
}

ostream &putUtf16(ostream &out, uint16_t utf16)
{
	if      (utf16 < 0x80 )
		out << (char)(utf16);
	else if (utf16 < 0x800)
		out << (char)(utf16 >>  6 | 0xC0) << (char)(utf16 & 0x3F | 0x80);
	else
		out << (char)(utf16 >> 12        | 0xE0)
				<< (char)(utf16 >>  6 & 0x3F | 0x80)
				<< (char)(utf16       & 0x3F | 0x80);

	return out;
}

istream &getline(istream &in, string &line, const string &delimiter)
{
	if (delimiter.empty()) return getline(in, line);

	getline(in, line, delimiter[delimiter.size() - 1]);
	while (delimiter.size() > line.size() && line.size()
			|| delimiter.size() > 1 && strcmp(delimiter.c_str(),
			line.c_str() + line.size() - delimiter.size() + 1))
	{
		line += delimiter[delimiter.size() - 1];
		getline(in, line, delimiter[delimiter.size() - 1]);
	}
	if (delimiter.size() > 1)
		line.resize(line.size() - delimiter.size() + 1);

	return in;
}

inline void skip(istream &in, const char *separator)
{
	for (const char *p = separator; *p; p ++)
		if (in.get() != *p) { in.unget(); break; }
}

// temporary directory

string tmpdir;

// generated structs and functions

""" + container.code + """

int main(int argc, char **argv)
{
	bool printing = false;
	bool last     = false;

	vector<char *> args(argv + 1, argv + argc);

	while (!last && !args.empty() && args[0][0] == '-')
	{
		if (args[0] == string("-d") && args.size() > 1)
		{
			tmpdir = args[1];
			args.erase(args.begin());
		}
		else if (args[0] == string("-p")) printing = true;
		else if (args[0] == string("--")) last     = true;

		args.erase(args.begin());
	}

	if (args.empty())
	{
		if (!tmpdir.empty())
		{
			build_0(cin);
		}
		else
		{
			Container<""" + container.type + """>::std_value_type std_container;

			get_0(cin, std_container);

			Container<""" + container.type + """>::build(
					ostreambuf_iterator<char>(cout), &std_container, &std_container + 1);
		}
	}
""" + ("key" in container.m.groupdict() and """\
	else if (printing && !args.empty())
	{
		static const string sep = """ + '\"' + container.m.group("sep"
				in container.m.groupdict() and "sep" or "keysep") + '\"' + """;

		Container<""" + container.type + """> container(args[0]);

		Container<""" + container.key.type + """>::std_value_type k;

		string line;
		while (getline(cin, line, sep))
		{
			istringstream isk(line);
			if (get_1(isk, k) == 0)
			{
""" + ("sub" not in container.m.groupdict() and """\
				cout << container[0](k);
""" or """\
				put_2(cout, container[0](k));
""") + """\
				cout << sep;
			}
		}
	}
""" or " ") + """\
	else for (int i = 0; i != args.size(); i ++)
	{
		Container<""" + container.type + """> container(args[i]);

		put_0(cout, container[0]);
	}

	return 0;
}
""" ""

tmpdir = tempfile.mkdtemp()

if not options.compile and os.getenv("FASTTRIE_COMPILE"):
	options.compile = os.getenv("FASTTRIE_COMPILE")
if options.compile:
	exe = options.compile + "/" + md5.new(options.format).hexdigest()
	try:
		if not os.path.exists(options.compile):
			os.makedirs(options.compile)
		if not os.path.exists(exe + ".cpp") or not os.stat(exe + ".cpp").st_size:
			file(exe + ".cpp", "w").write(cpp)
	except: pass
else:
	exe = tmpdir + "/fasttrie"

def kill_handler(signum, frame):
	raise KeyboardInterrupt # treat kill as KeyboardInterrupt

signal.signal(signal.SIGTERM, kill_handler)

# compile and run

try:
	if sys.version_info >= (2, 4):
		if not os.access(exe, os.X_OK) or not os.stat(exe).st_size:
			p = subprocess.Popen(["g++", "-x", "c++", "-o", exe, "-O3", "-"]
					+ (options.include and ["-I", options.include] or [])
					+ (os.path.dirname(sys.argv[0])
								and ["-I", os.path.dirname(sys.argv[0])] or []),
					stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
			(out, err) = p.communicate(input=cpp)
			if out or err or \
					not os.access(exe, os.X_OK) or not os.stat(exe).st_size: raise

		p = subprocess.Popen([exe]
				+ (options.disk     and ["-d", tmpdir] or [])
				+ (options.printing and ["-p"        ] or []) + ["--"] + args)
		p.wait()
	else:
		if not os.access(exe, os.X_OK) or not os.stat(exe).st_size:
			(out, input, err) = popen2.popen3("g++ -x c++ -o '" + exe + "' -O3 -"
					+ (options.include and " -I '" + options.include + "'" or "")
					+ (os.path.dirname(sys.argv[0])
								and " -I '" + os.path.dirname(sys.argv[0]) + "'" or ""))
			input.write(cpp)
			input.close()
			out = out.read()
			err = err.read()
			if out or err or \
					not os.access(exe, os.X_OK) or not os.stat(exe).st_size: raise

		(out, input, err) = popen2.popen3("'" + exe + "' "
				+ (options.disk     and "-d '" + tmpdir + "' " or "")
				+ (options.printing and "-p "                  or "")
				+ "-- " + " ".join(map(lambda x: "'" + x + "'", args)))
		if not args:
			for line in sys.stdin:
				input.write(line)
		elif args and options.printing:
			while True:
				line = sys.stdin.readline()
				if not line: break
				input.write(line)
				input.flush()
				sys.stdout.write(out.readline())
				sys.stdout.flush()
		input.close()
		data = out.read(1048576)
		while data:
			sys.stdout.write(data)
			data = out.read(1048576)

except KeyboardInterrupt: pass
except:
	shutil.rmtree(tmpdir)
	if not "err" in locals(): err = ""
	if not isinstance(err, str): err = err.read()
	sys.stderr.write(err)
	sys.stderr.write(os.path.basename(sys.argv[0]) + ": compile or execute failed\n")
	sys.exit(-1)

shutil.rmtree(tmpdir)
