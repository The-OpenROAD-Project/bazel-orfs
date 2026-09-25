// odb_codec on a synthetic file shaped like a .odb: a header, a table of
// fixed-length slots, a table whose slots vary in length, a table too
// small to reformat, and bytes in between that belong to no table.
#include <algorithm>
#include <iostream>
#include <string>

#include "odb_codec.h"

#define CHECK(cond)                                                       \
  do {                                                                    \
    if (!(cond)) {                                                        \
      std::cerr << __FILE__ << ":" << __LINE__ << ": CHECK failed: " #cond \
                << "\n";                                                  \
      return 1;                                                           \
    }                                                                     \
  } while (0)

namespace {

struct Synthetic {
  std::string odb;
  std::string layout = "odb-layout 1\n";

  void Bytes(const std::string& bytes) { odb += bytes; }

  // count slots of table, each made by slot(i).
  template <typename F>
  void Table(const std::string& table, int count, F slot) {
    for (int i = 0; i < count; ++i) {
      const std::string bytes = slot(i);
      layout += table + " " + std::to_string(odb.size()) + " " +
                std::to_string(bytes.size()) + " 1\n";
      odb += bytes;
    }
  }

  std::string Layout() const {
    return layout + "size " + std::to_string(odb.size()) + "\n";
  }
};

// `moved` shifts every dbInst slot's third byte, as a placer moves
// cells; `grown` adds slots to dbNet, as a resizer adds nets.
Synthetic Make(int moved = 0, int grown = 0) {
  Synthetic s;
  s.Bytes("header: not a table");
  // Every slot has 'Q' at byte 1, so the encoding holds a run of 300 of
  // them.
  s.Table("dbInst", 300, [moved](int i) {
    return std::string{'\1', 'Q', static_cast<char>(i + moved),
                       static_cast<char>(i >> 8), '\0', '\0', '\0', '\7'};
  });
  s.Bytes(moved ? "a hash table, sat" : "a hash table, say");
  s.Table("dbNet", 50 + grown, [](int i) {
    return std::string(1, '\1') + std::string(1 + i % 3, static_cast<char>('a' + i));
  });
  s.Table("dbTiny", 3, [](int i) { return std::string(4, static_cast<char>(i)); });
  // A list through a permutation of the slots, as net iterms are: next
  // and prev are inverses, and a creation-order chain points at id + 1.
  s.Table("dbList", 400, [](int i) {
    auto u32 = [](uint32_t v) {
      return std::string{static_cast<char>(v), static_cast<char>(v >> 8),
                         static_cast<char>(v >> 16), static_cast<char>(v >> 24)};
    };
    const uint32_t order = (i * 7) % 400;  // this slot's place in the list
    const uint32_t next = order == 399 ? 0 : ((order + 1) * 343) % 400 + 1;
    const uint32_t prev = order == 0 ? 0 : ((order - 1) * 343) % 400 + 1;
    return std::string(1, '\1') + u32(next) + u32(prev) + u32(i + 1) +
           u32(i * 2654435761u);
  });
  s.Bytes("trailer");
  return s;
}

}  // namespace

int main() {
  const Synthetic s = Make();
  std::string encoded;
  std::string decoded;
  std::string error;

  // Round trip, and the encoding is really reformatted.
  CHECK(!odb_codec::IsEncoded(s.odb));
  CHECK(odb_codec::Encode(s.odb, s.Layout(), &encoded, &error));
  CHECK(odb_codec::IsEncoded(encoded));
  CHECK(encoded.find(std::string(300, 'Q')) != std::string::npos);
  CHECK(odb_codec::Decode(encoded, nullptr, &decoded, &error));
  CHECK(decoded == s.odb);
  // prev is the inverse of next and the third field is id + 1, so both
  // become columns of zeros: 800 slot bytes of each, as four planes.
  CHECK(encoded.find(std::string(4 * 400, '\0')) != std::string::npos);

  // A layout that names no slots still round-trips.
  const std::string empty = "odb-layout 1\nsize " + std::to_string(s.odb.size()) + "\n";
  CHECK(odb_codec::Encode(s.odb, empty, &encoded, &error));
  CHECK(odb_codec::Decode(encoded, nullptr, &decoded, &error));
  CHECK(decoded == s.odb);

  // A layout that does not describe the file is refused.
  CHECK(!odb_codec::Encode(s.odb + "x", s.Layout(), &encoded, &error));
  CHECK(!odb_codec::Encode(s.odb, "odb-layout 2\nsize 0\n", &encoded, &error));
  CHECK(!odb_codec::Encode(s.odb, "odb-layout 1\n", &encoded, &error));
  const std::string size = "size " + std::to_string(s.odb.size()) + "\n";
  CHECK(!odb_codec::Encode(s.odb, "odb-layout 1\nt 10 4 2\nt 12 4 1\n" + size,
                           &encoded, &error));
  CHECK(!odb_codec::Encode(s.odb, "odb-layout 1\nt 0 4 1000000\n" + size,
                           &encoded, &error));
  CHECK(!odb_codec::Encode(s.odb, "odb-layout 1\nt 99999999 1 1\n" + size,
                           &encoded, &error));

  // Every truncation of an encoded file is refused, none crashes.
  CHECK(odb_codec::Encode(s.odb, s.Layout(), &encoded, &error));
  for (size_t n = 0; n < encoded.size(); ++n) {
    CHECK(!odb_codec::Decode(encoded.substr(0, n), nullptr, &decoded, &error));
  }
  // A delta against an earlier state of the same flow, and back.
  const Synthetic before = Make();
  const Synthetic after = Make(3, 20);
  std::string base_encoded;
  CHECK(odb_codec::Encode(before.odb, before.Layout(), &base_encoded, &error));
  std::string standalone;
  CHECK(odb_codec::Encode(after.odb, after.Layout(), &standalone, &error));
  std::string delta;
  CHECK(odb_codec::EncodeDelta(standalone, after.odb, "before.odb",
                               base_encoded, before.odb, &delta, &error));
  std::string base_name;
  CHECK(odb_codec::BaseOf(delta, &base_name, &error) &&
        base_name == "before.odb");
  auto base = [&](const std::string& name, std::string* e, std::string* o,
                  std::string*) {
    if (name != "before.odb") {
      return false;
    }
    *e = base_encoded;
    *o = before.odb;
    return true;
  };
  CHECK(odb_codec::Decode(delta, base, &decoded, &error));
  CHECK(decoded == after.odb);
  // What the delta leaves is mostly zeros, for the compressor to remove.
  auto nonzero = [](const std::string& b) {
    return std::count_if(b.begin(), b.end(), [](char c) { return c != 0; });
  };
  CHECK(nonzero(delta) * 2 < nonzero(standalone));

  // The base may be in any encoded form, a delta itself included.
  std::string identical;
  CHECK(odb_codec::EncodeDelta(base_encoded, before.odb, "before.odb",
                               base_encoded, before.odb, &identical, &error));
  CHECK(identical.size() * 4 < base_encoded.size());
  CHECK(odb_codec::Decode(identical, base, &decoded, &error));
  CHECK(decoded == before.odb);
  std::string on_identical;
  CHECK(odb_codec::EncodeDelta(standalone, after.odb, "before.odb", identical,
                               before.odb, &on_identical, &error));
  CHECK(odb_codec::Decode(on_identical, base, &decoded, &error));
  CHECK(decoded == after.odb);

  // A missing base, or another file under its name, is refused.
  CHECK(!odb_codec::Decode(delta, nullptr, &decoded, &error));
  auto wrong = [&](const std::string&, std::string* e, std::string* o,
                   std::string*) {
    *e = standalone;
    *o = after.odb;
    return true;
  };
  CHECK(!odb_codec::Decode(delta, wrong, &decoded, &error));
  CHECK(error.find("not the file") != std::string::npos);
  for (size_t n = 0; n < delta.size(); ++n) {
    CHECK(!odb_codec::Decode(delta.substr(0, n), base, &decoded, &error));
  }
  std::cout << "odb_codec_test: delta " << nonzero(delta)
            << " nonzero bytes against " << nonzero(standalone)
            << " standalone\n";

  std::cout << "odb_codec_test: " << s.odb.size() << " bytes, "
            << encoded.size() << " encoded, round trip ok\n";
  return 0;
}
