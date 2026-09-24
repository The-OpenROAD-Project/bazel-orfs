// odb_codec: the ODB_CODEC OpenROAD's read_db and write_db run. See
// odb_codec.h.
#include <cstdio>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

#include "odb_codec.h"

namespace {

bool ReadFile(const std::string& path, std::string* bytes) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return false;
  }
  std::ostringstream buffer;
  buffer << in.rdbuf();
  *bytes = std::move(buffer).str();
  return static_cast<bool>(in);
}

// Replaces path by bytes, all at once.
bool WriteFile(const std::string& path, const std::string& bytes) {
  const std::string tmp = path + ".odb_codec";
  {
    std::ofstream out(tmp, std::ios::binary | std::ios::trunc);
    out.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    if (!out.flush()) {
      std::remove(tmp.c_str());
      return false;
    }
  }
  return std::rename(tmp.c_str(), path.c_str()) == 0;
}

// Reformats the file in place. When it cannot, the file is left exactly
// as OpenROAD wrote it: a warning, not a failure, since that file is
// still a correct .odb and decode hands it over unchanged.
int Encode(const std::string& path, const std::string& layout_path) {
  std::string odb;
  std::string layout;
  if (!ReadFile(path, &odb) || !ReadFile(layout_path, &layout)) {
    std::cerr << "odb_codec: cannot read " << path << " or " << layout_path
              << "\n";
    return 1;
  }
  std::string encoded;
  std::string error;
  if (!odb_codec::Encode(odb, layout, &encoded, &error)) {
    std::cerr << "odb_codec: " << path << " left as written: " << error
              << "\n";
    return 0;
  }
  // Checked here rather than trusted: this is the one place a codec bug
  // could still be caught before the original bytes are gone.
  std::string decoded;
  if (!odb_codec::Decode(encoded, &decoded, &error) || decoded != odb) {
    std::cerr << "odb_codec: " << path
              << " left as written: encoding did not round-trip\n";
    return 0;
  }
  if (!WriteFile(path, encoded)) {
    std::cerr << "odb_codec: cannot write " << path << "\n";
    return 1;
  }
  return 0;
}

// Writes the .odb to stdout: decoded when encode wrote it, otherwise as
// it is.
int Decode(const std::string& path) {
  std::string bytes;
  if (!ReadFile(path, &bytes)) {
    std::cerr << "odb_codec: cannot read " << path << "\n";
    return 1;
  }
  if (odb_codec::IsEncoded(bytes)) {
    std::string decoded;
    std::string error;
    if (!odb_codec::Decode(bytes, &decoded, &error)) {
      std::cerr << "odb_codec: " << path << ": " << error << "\n";
      return 1;
    }
    bytes = std::move(decoded);
  }
  if (std::fwrite(bytes.data(), 1, bytes.size(), stdout) != bytes.size() ||
      std::fflush(stdout) != 0) {
    std::cerr << "odb_codec: cannot write " << path << " to stdout\n";
    return 1;
  }
  return 0;
}

}  // namespace

int main(int argc, char** argv) {
  const std::string verb = argc > 1 ? argv[1] : "";
  if (verb == "encode" && argc == 4) {
    return Encode(argv[2], argv[3]);
  }
  if (verb == "decode" && argc == 3) {
    return Decode(argv[2]);
  }
  std::cerr << "usage: odb_codec encode FILE LAYOUT   reformat FILE in place\n"
               "       odb_codec decode FILE          the .odb, on stdout\n";
  return 2;
}
