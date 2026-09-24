// odb_codec: see odb_codec.h.
//
// A .odb writes each table's slots one after another, each slot a row of
// fixed-width fields. Neighbouring bytes therefore belong to unrelated
// fields, and a compressor never sees a run longer than one field. The
// encoding gathers every slot of one table and one length into a matrix
// and writes it column by column: byte 0 of every slot, then byte 1, and
// so on. It is the same bytes in another order; nothing is modelled,
// predicted or compressed here. Compression is left to whatever stores
// or ships the file.
//
// Encoded file, all integers LEB128 varints:
//
//   "ODBCODEC"                         magic, 8 bytes
//   version                            1
//   size                               bytes of the original .odb
//   groups, then per group:            one table at one slot length
//     name length, name, slot length, slots
//   runs, then per run:                in file order
//     gap, group, slots                gap: original bytes before the run
//   verbatim length, verbatim bytes    every byte in no run, in order
//   per group: its matrix, column by column
#include "odb_codec.h"

#include <cstdint>
#include <map>
#include <sstream>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace odb_codec {
namespace {

constexpr std::string_view kMagic = "ODBCODEC";
constexpr uint64_t kVersion = 1;

// A group with fewer slots than this stays where it is: a column of a
// handful of bytes gains nothing and costs a group header.
constexpr uint64_t kMinGroupSlots = 8;

struct Run {
  uint64_t offset;
  uint64_t length;
  uint64_t count;
  std::string table;
};

struct Group {
  std::string table;
  uint64_t length = 0;
  uint64_t slots = 0;
};

void PutVarint(std::string* out, uint64_t v) {
  while (v >= 0x80) {
    out->push_back(static_cast<char>((v & 0x7f) | 0x80));
    v >>= 7;
  }
  out->push_back(static_cast<char>(v));
}

class Reader {
 public:
  explicit Reader(std::string_view bytes) : bytes_(bytes) {}

  bool Varint(uint64_t* v) {
    *v = 0;
    for (int shift = 0; shift < 64; shift += 7) {
      if (pos_ >= bytes_.size()) {
        return false;
      }
      const uint8_t b = static_cast<uint8_t>(bytes_[pos_++]);
      *v |= static_cast<uint64_t>(b & 0x7f) << shift;
      if ((b & 0x80) == 0) {
        return true;
      }
    }
    return false;
  }

  bool Bytes(uint64_t n, std::string_view* out) {
    if (n > bytes_.size() - pos_) {
      return false;
    }
    *out = bytes_.substr(pos_, n);
    pos_ += n;
    return true;
  }

 private:
  std::string_view bytes_;
  size_t pos_ = 0;
};

bool ParseLayout(std::string_view text, uint64_t size, std::vector<Run>* runs,
                 std::string* error) {
  std::istringstream in{std::string(text)};
  std::string word;
  int version = 0;
  if (!(in >> word >> version) || word != "odb-layout" || version != 1) {
    *error = "not an odb-layout 1 file";
    return false;
  }
  uint64_t end = 0;
  while (in >> word) {
    if (word == "size") {
      uint64_t described = 0;
      if (!(in >> described) || described != size) {
        *error = "layout describes a file of another size";
        return false;
      }
      return true;
    }
    Run run{0, 0, 0, word};
    if (!(in >> run.offset >> run.length >> run.count) || run.length == 0 ||
        run.count == 0) {
      *error = "malformed run for table " + word;
      return false;
    }
    if (run.offset < end || run.offset > size ||
        run.count > (size - run.offset) / run.length) {
      *error = "run for table " + word + " is out of order or out of bounds";
      return false;
    }
    end = run.offset + run.length * run.count;
    runs->push_back(std::move(run));
  }
  *error = "layout has no size line";
  return false;
}

}  // namespace

bool IsEncoded(std::string_view bytes) {
  return bytes.substr(0, kMagic.size()) == kMagic;
}

bool Encode(std::string_view odb, std::string_view layout, std::string* out,
            std::string* error) {
  std::vector<Run> runs;
  if (!ParseLayout(layout, odb.size(), &runs, error)) {
    return false;
  }

  // Groups, keyed by table and slot length, numbered in first-seen order.
  std::map<std::pair<std::string, uint64_t>, size_t> index;
  std::vector<Group> groups;
  std::vector<size_t> run_group;
  for (const Run& run : runs) {
    auto [it, added] =
        index.try_emplace({run.table, run.length}, groups.size());
    if (added) {
      groups.push_back(Group{run.table, run.length, 0});
    }
    groups[it->second].slots += run.count;
    run_group.push_back(it->second);
  }

  // Groups too small to gain anything are dropped, and their runs with
  // them: those bytes stay in the verbatim stream.
  std::vector<size_t> renumber(groups.size(), SIZE_MAX);
  std::vector<Group> kept;
  for (size_t g = 0; g < groups.size(); ++g) {
    if (groups[g].slots >= kMinGroupSlots) {
      renumber[g] = kept.size();
      kept.push_back(groups[g]);
    }
  }

  std::vector<std::string> matrix(kept.size());
  for (size_t g = 0; g < kept.size(); ++g) {
    matrix[g].reserve(kept[g].length * kept[g].slots);
  }
  // Runs as the encoding lists them: a run that continues the previous
  // one's group with no bytes in between is merged into it.
  struct Placed {
    uint64_t gap;
    size_t group;
    uint64_t count;
  };
  std::vector<Placed> placed;
  std::string verbatim;
  uint64_t pos = 0;
  for (size_t r = 0; r < runs.size(); ++r) {
    const size_t g = renumber[run_group[r]];
    if (g == SIZE_MAX) {
      continue;
    }
    const Run& run = runs[r];
    const uint64_t gap = run.offset - pos;
    verbatim.append(odb.substr(pos, gap));
    if (gap == 0 && !placed.empty() && placed.back().group == g) {
      placed.back().count += run.count;
    } else {
      placed.push_back(Placed{gap, g, run.count});
    }
    matrix[g].append(odb.substr(run.offset, run.length * run.count));
    pos = run.offset + run.length * run.count;
  }
  verbatim.append(odb.substr(pos));

  out->clear();
  out->append(kMagic);
  PutVarint(out, kVersion);
  PutVarint(out, odb.size());
  PutVarint(out, kept.size());
  for (const Group& group : kept) {
    PutVarint(out, group.table.size());
    out->append(group.table);
    PutVarint(out, group.length);
    PutVarint(out, group.slots);
  }
  PutVarint(out, placed.size());
  for (const Placed& run : placed) {
    PutVarint(out, run.gap);
    PutVarint(out, run.group);
    PutVarint(out, run.count);
  }
  PutVarint(out, verbatim.size());
  out->append(verbatim);
  for (size_t g = 0; g < kept.size(); ++g) {
    // Rows to columns.
    const uint64_t length = kept[g].length;
    const uint64_t slots = kept[g].slots;
    const size_t start = out->size();
    out->resize(start + length * slots);
    char* columns = out->data() + start;
    const char* rows = matrix[g].data();
    for (uint64_t s = 0; s < slots; ++s) {
      for (uint64_t b = 0; b < length; ++b) {
        columns[b * slots + s] = rows[s * length + b];
      }
    }
  }
  return true;
}

bool Decode(std::string_view encoded, std::string* out, std::string* error) {
  *error = "truncated or corrupt encoded .odb";
  if (!IsEncoded(encoded)) {
    *error = "not an encoded .odb";
    return false;
  }
  Reader in(encoded.substr(kMagic.size()));
  uint64_t version = 0;
  uint64_t size = 0;
  uint64_t group_count = 0;
  if (!in.Varint(&version) || version != kVersion) {
    *error = "encoded .odb of an unknown version";
    return false;
  }
  if (!in.Varint(&size) || !in.Varint(&group_count)) {
    return false;
  }
  std::vector<Group> groups(group_count);
  for (Group& group : groups) {
    uint64_t name_length = 0;
    std::string_view name;
    if (!in.Varint(&name_length) || !in.Bytes(name_length, &name) ||
        !in.Varint(&group.length) || !in.Varint(&group.slots)) {
      return false;
    }
    group.table = name;
  }
  struct Placed {
    uint64_t gap;
    uint64_t group;
    uint64_t count;
  };
  uint64_t run_count = 0;
  if (!in.Varint(&run_count)) {
    return false;
  }
  std::vector<Placed> runs;
  for (uint64_t r = 0; r < run_count; ++r) {
    Placed run{};
    if (!in.Varint(&run.gap) || !in.Varint(&run.group) ||
        !in.Varint(&run.count) || run.group >= groups.size()) {
      return false;
    }
    runs.push_back(run);
  }
  uint64_t verbatim_length = 0;
  std::string_view verbatim;
  if (!in.Varint(&verbatim_length) || !in.Bytes(verbatim_length, &verbatim)) {
    return false;
  }
  // Columns back to rows, one group at a time.
  std::vector<std::string> rows(groups.size());
  for (size_t g = 0; g < groups.size(); ++g) {
    const uint64_t length = groups[g].length;
    const uint64_t slots = groups[g].slots;
    std::string_view columns;
    if (length != 0 && slots > UINT64_MAX / length) {
      return false;
    }
    if (!in.Bytes(length * slots, &columns)) {
      return false;
    }
    rows[g].resize(length * slots);
    for (uint64_t s = 0; s < slots; ++s) {
      for (uint64_t b = 0; b < length; ++b) {
        rows[g][s * length + b] = columns[b * slots + s];
      }
    }
  }

  out->clear();
  out->reserve(size);
  std::vector<uint64_t> taken(groups.size(), 0);
  size_t vpos = 0;
  for (const Placed& run : runs) {
    const Group& group = groups[run.group];
    if (run.gap > verbatim.size() - vpos ||
        run.count > group.slots - taken[run.group]) {
      return false;
    }
    out->append(verbatim.substr(vpos, run.gap));
    vpos += run.gap;
    out->append(rows[run.group], taken[run.group] * group.length,
                run.count * group.length);
    taken[run.group] += run.count;
  }
  out->append(verbatim.substr(vpos));
  for (size_t g = 0; g < groups.size(); ++g) {
    if (taken[g] != groups[g].slots) {
      return false;
    }
  }
  if (out->size() != size) {
    return false;
  }
  error->clear();
  return true;
}

}  // namespace odb_codec
