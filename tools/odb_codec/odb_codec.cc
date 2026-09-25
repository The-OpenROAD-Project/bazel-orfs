// odb_codec: see odb_codec.h.
//
// A .odb writes each table's slots one after another, each slot a row of
// fixed-width fields. Neighbouring bytes therefore belong to unrelated
// fields, and a compressor never sees a run longer than one field. The
// encoding gathers every slot of one table and one length into a matrix
// and writes it column by column: byte 0 of every slot, then byte 1, and
// so on. Compression is left to whatever stores or ships the file.
//
// Before that, a 4-byte field that another field or the slot's own id
// predicts is replaced by what the prediction misses: a list's prev
// pointers are the inverse of its next pointers, a chain built in
// creation order points at the next id, and some fields repeat others.
// Nothing here knows which field is which; a predictor is kept for a
// field when it is right for more than half of the group's slots, and
// since the residual is exact, a wrong guess costs bytes, never
// correctness.
//
// A delta stores a file against a base, another .odb of the same flow:
// each slot as its difference from the slot with the same table,
// instance and id in the base (4-byte fields subtracted, other bytes
// xor-ed), and the bytes in no slot as copies from the base's and
// literals. A slot without a partner of its length is stored as is. A
// file identical to its base is stored as just that.
//
// Encoded file, all integers LEB128 varints:
//
//   "ODBCODEC"                         magic, 8 bytes
//   version                            3
//   size                               bytes of the original .odb
//   mode                               0 standalone, 1 delta, 2 identical
//   unless standalone:                 the base
//     name length, name, size, FNV-1a 64 hash of its original bytes
//   groups, then per group:            one table at one slot length
//     name length, name, slot length, slots
//     predictors, then per predictor:  field offset, kind, parameter
//   runs, then per run:                in file order
//     gap                              original bytes before the run
//     group, slots
//     table instance, minus the previous run's
//     id of the first slot, minus the id that follows the previous run
//       of the same instance (0 when the instance is new)
//   standalone:                        every byte in no run, in order
//     verbatim length, verbatim bytes
//   delta:                             the same, against the base's
//     ops, then per op: literal length, copy length, copy offset minus
//       the end of the previous copy (zigzag)
//     literals length, literals
//   per group, unless identical:       its matrix, column by column
//
// Every form of a file carries the same groups and runs, so a base read
// while another process rewrites it has the same slots either way.
#include "odb_codec.h"

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

namespace odb_codec {
namespace {

constexpr std::string_view kMagic = "ODBCODEC";
constexpr uint64_t kVersion = 3;

// A group with fewer slots than this stays where it is: a column of a
// handful of bytes gains nothing and costs a group header.
constexpr uint64_t kMinGroupSlots = 8;

// Fields are paired with each other only in slots of at most this many,
// so that trying predictors stays linear in the file.
constexpr uint64_t kMaxPairedFields = 32;

// Predictors. A slot's id is its position in its table: dbTable writes
// every slot of every page in order, so that is also the object id.
enum Kind : uint64_t {
  kId = 0,       // the slot's id plus a small constant
  kCopy = 1,     // another field of the same slot
  kInverse = 2,  // the id of the slot whose other field names this one
};

struct Predictor {
  uint64_t offset;
  uint64_t kind;
  uint64_t param;  // kId: the constant, zigzag; otherwise the other field
};

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
  std::vector<Predictor> predictors;
};

// Where each slot of a group sits in its table.
struct SlotIds {
  std::vector<uint32_t> id;
  std::vector<uint32_t> instance;
};

void PutVarint(std::string* out, uint64_t v) {
  while (v >= 0x80) {
    out->push_back(static_cast<char>((v & 0x7f) | 0x80));
    v >>= 7;
  }
  out->push_back(static_cast<char>(v));
}

uint64_t ZigZag(int64_t v) {
  return (static_cast<uint64_t>(v) << 1) ^ static_cast<uint64_t>(v >> 63);
}

int64_t UnZigZag(uint64_t v) {
  return static_cast<int64_t>(v >> 1) ^ -static_cast<int64_t>(v & 1);
}

uint32_t Load(const char* p) {
  const auto* b = reinterpret_cast<const unsigned char*>(p);
  return uint32_t{b[0]} | uint32_t{b[1]} << 8 | uint32_t{b[2]} << 16 |
         uint32_t{b[3]} << 24;
}

void Store(char* p, uint32_t v) {
  for (int i = 0; i < 4; ++i) {
    p[i] = static_cast<char>(v >> (8 * i));
  }
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

// The id of the slot whose field at `offset` holds each value, by table
// instance; nullopt when two slots hold the same nonzero value.
using InverseMap = std::unordered_map<uint64_t, uint32_t>;

std::optional<InverseMap> Inverse(const std::string& rows, uint64_t length,
                                  uint64_t offset, const SlotIds& ids) {
  InverseMap map;
  const uint64_t slots = ids.id.size();
  map.reserve(slots);
  for (uint64_t s = 0; s < slots; ++s) {
    const uint32_t v = Load(rows.data() + s * length + offset);
    if (v == 0) {
      continue;
    }
    const uint64_t key = uint64_t{ids.instance[s]} << 32 | v;
    if (!map.emplace(key, ids.id[s]).second) {
      return std::nullopt;
    }
  }
  return map;
}

// Every slot's value of the field at `offset`.
std::vector<uint32_t> Column(const std::string& rows, uint64_t length,
                             uint64_t offset, uint64_t slots) {
  std::vector<uint32_t> column(slots);
  for (uint64_t s = 0; s < slots; ++s) {
    column[s] = Load(rows.data() + s * length + offset);
  }
  return column;
}

// What an inverse predictor from `map` predicts for every slot.
std::vector<uint32_t> InversePrediction(const InverseMap& map,
                                        const SlotIds& ids) {
  std::vector<uint32_t> predicted(ids.id.size());
  for (size_t s = 0; s < predicted.size(); ++s) {
    const auto it = map.find(uint64_t{ids.instance[s]} << 32 | ids.id[s]);
    predicted[s] = it == map.end() ? 0 : it->second;
  }
  return predicted;
}

// Chooses the group's predictors and replaces each predicted field by its
// residual. A field that another is predicted from stays as it is, and a
// predicted field is never the source of another, so the decoder can
// undo them in any order.
std::vector<Predictor> ApplyPredictors(std::string* rows, uint64_t length,
                                       const SlotIds& ids) {
  const uint64_t slots = ids.id.size();
  if (length < 5 || slots == 0) {
    return {};
  }
  std::vector<uint64_t> fields;
  for (uint64_t o = 1; o + 4 <= length; o += 4) {
    fields.push_back(o);
  }
  const bool paired = fields.size() <= kMaxPairedFields;
  // Each field's values, and what each possible prediction says, once.
  std::map<uint64_t, std::vector<uint32_t>> column;
  std::map<uint64_t, std::vector<uint32_t>> inverse;
  for (uint64_t o : fields) {
    column[o] = Column(*rows, length, o, slots);
    if (paired) {
      if (auto map = Inverse(*rows, length, o, ids)) {
        inverse[o] = InversePrediction(*map, ids);
      }
    }
  }
  auto hits = [&](const std::vector<uint32_t>& actual, auto&& predicted) {
    uint64_t n = 0;
    for (uint64_t s = 0; s < slots; ++s) {
      n += actual[s] == predicted(s);
    }
    return n;
  };
  struct Choice {
    uint64_t hits;
    Predictor predictor;
  };
  std::vector<Choice> choices;
  auto keep = [&](uint64_t n, const Predictor& p) {
    if (n * 2 > slots) {
      choices.push_back(Choice{n, p});
    }
  };
  for (uint64_t o : fields) {
    const std::vector<uint32_t>& actual = column[o];
    for (int64_t c = -1; c <= 1; ++c) {
      const auto k = static_cast<uint32_t>(c);
      keep(hits(actual, [&](uint64_t s) { return ids.id[s] + k; }),
           Predictor{o, kId, ZigZag(c)});
    }
    if (!paired) {
      continue;
    }
    for (uint64_t a : fields) {
      if (a == o) {
        continue;
      }
      const std::vector<uint32_t>& other = column[a];
      keep(hits(actual, [&](uint64_t s) { return other[s]; }),
           Predictor{o, kCopy, a});
      const auto it = inverse.find(a);
      if (it != inverse.end()) {
        const std::vector<uint32_t>& inv = it->second;
        keep(hits(actual, [&](uint64_t s) { return inv[s]; }),
             Predictor{o, kInverse, a});
      }
    }
  }
  std::stable_sort(choices.begin(), choices.end(),
                   [](const Choice& x, const Choice& y) {
                     return x.hits > y.hits;
                   });
  std::vector<Predictor> chosen;
  std::vector<bool> source(length, false);
  std::vector<bool> predicted(length, false);
  for (const Choice& choice : choices) {
    const Predictor& p = choice.predictor;
    if (predicted[p.offset] || source[p.offset] ||
        (p.kind != kId && predicted[p.param])) {
      continue;
    }
    predicted[p.offset] = true;
    if (p.kind != kId) {
      source[p.param] = true;
    }
    chosen.push_back(p);
  }
  // Sources are never predicted, so the columns read above are still
  // every prediction's inputs.
  for (const Predictor& p : chosen) {
    const std::vector<uint32_t>& actual = column[p.offset];
    for (uint64_t s = 0; s < slots; ++s) {
      uint32_t guess;
      switch (p.kind) {
        case kId:
          guess = ids.id[s] + static_cast<uint32_t>(UnZigZag(p.param));
          break;
        case kCopy:
          guess = column[p.param][s];
          break;
        default:
          guess = inverse[p.param][s];
      }
      Store(rows->data() + s * length + p.offset, actual[s] - guess);
    }
  }
  return chosen;
}

bool UndoPredictors(const std::vector<Predictor>& predictors,
                    std::string* rows, uint64_t length, const SlotIds& ids) {
  const uint64_t slots = ids.id.size();
  // Sources are never predicted, so their values are already the
  // original ones: read every input before writing any field.
  std::map<uint64_t, std::vector<uint32_t>> guesses;
  for (const Predictor& p : predictors) {
    if (p.offset + 4 > length || (p.kind != kId && p.param + 4 > length) ||
        p.kind > kInverse) {
      return false;
    }
    std::vector<uint32_t> guess(slots);
    if (p.kind == kId) {
      const auto k = static_cast<uint32_t>(UnZigZag(p.param));
      for (uint64_t s = 0; s < slots; ++s) {
        guess[s] = ids.id[s] + k;
      }
    } else if (p.kind == kCopy) {
      guess = Column(*rows, length, p.param, slots);
    } else {
      auto map = Inverse(*rows, length, p.param, ids);
      if (!map) {
        return false;
      }
      guess = InversePrediction(*map, ids);
    }
    guesses[p.offset] = std::move(guess);
  }
  for (const auto& [offset, guess] : guesses) {
    for (uint64_t s = 0; s < slots; ++s) {
      char* field = rows->data() + s * length + offset;
      Store(field, Load(field) + guess[s]);
    }
  }
  return true;
}


enum Mode : uint64_t {
  kStandalone = 0,
  kDelta = 1,
  kIdentical = 2,
};

struct BaseRef {
  std::string name;
  uint64_t size = 0;
  uint64_t hash = 0;
};

struct PlacedRun {
  uint64_t gap;
  uint64_t group;
  uint64_t count;
  uint64_t instance;
  uint64_t id;
};

// An encoded file, parsed but not decoded.
struct Parsed {
  uint64_t mode = kStandalone;
  uint64_t size = 0;
  BaseRef base;
  std::vector<Group> groups;
  std::vector<PlacedRun> runs;
  std::string_view verbatim;  // standalone
  uint64_t op_count = 0;      // delta
  std::string_view ops;
  std::string_view literals;
  std::vector<std::string_view> matrices;  // unless identical
};

uint64_t Hash(std::string_view bytes) {
  uint64_t h = 0xcbf29ce484222325ull;
  for (const char c : bytes) {
    h = (h ^ static_cast<unsigned char>(c)) * 0x100000001b3ull;
  }
  return h;
}

bool ParseContainer(std::string_view encoded, Parsed* p, std::string* error) {
  *error = "truncated or corrupt encoded .odb";
  if (encoded.substr(0, kMagic.size()) != kMagic) {
    *error = "not an encoded .odb";
    return false;
  }
  Reader in(encoded.substr(kMagic.size()));
  uint64_t version = 0;
  if (!in.Varint(&version) || version != kVersion) {
    *error = "encoded .odb of an unknown version";
    return false;
  }
  uint64_t group_count = 0;
  if (!in.Varint(&p->size) || !in.Varint(&p->mode) || p->mode > kIdentical) {
    return false;
  }
  if (p->mode != kStandalone) {
    uint64_t n = 0;
    std::string_view name;
    if (!in.Varint(&n) || !in.Bytes(n, &name) || !in.Varint(&p->base.size) ||
        !in.Varint(&p->base.hash)) {
      return false;
    }
    p->base.name = name;
  }
  if (!in.Varint(&group_count)) {
    return false;
  }
  for (uint64_t g = 0; g < group_count; ++g) {
    Group group;
    uint64_t name_length = 0;
    uint64_t predictor_count = 0;
    std::string_view name;
    if (!in.Varint(&name_length) || !in.Bytes(name_length, &name) ||
        !in.Varint(&group.length) || !in.Varint(&group.slots) ||
        !in.Varint(&predictor_count) || predictor_count > group.length) {
      return false;
    }
    group.table = name;
    for (uint64_t i = 0; i < predictor_count; ++i) {
      Predictor pr{};
      if (!in.Varint(&pr.offset) || !in.Varint(&pr.kind) ||
          !in.Varint(&pr.param)) {
        return false;
      }
      group.predictors.push_back(pr);
    }
    p->groups.push_back(std::move(group));
  }
  uint64_t run_count = 0;
  if (!in.Varint(&run_count)) {
    return false;
  }
  std::vector<uint64_t> taken(p->groups.size(), 0);
  uint64_t instance = 0;
  uint64_t last_end = 0;
  for (uint64_t r = 0; r < run_count; ++r) {
    PlacedRun run{};
    uint64_t instance_delta = 0;
    uint64_t id_delta = 0;
    if (!in.Varint(&run.gap) || !in.Varint(&run.group) ||
        !in.Varint(&run.count) || !in.Varint(&instance_delta) ||
        !in.Varint(&id_delta) || run.group >= p->groups.size() ||
        run.count > p->groups[run.group].slots - taken[run.group]) {
      return false;
    }
    taken[run.group] += run.count;
    instance += instance_delta;
    run.instance = instance;
    run.id = (instance_delta == 0 ? last_end : 0) + id_delta;
    last_end = run.id + run.count;
    p->runs.push_back(run);
  }
  for (size_t g = 0; g < p->groups.size(); ++g) {
    if (taken[g] != p->groups[g].slots) {
      return false;
    }
  }
  if (p->mode == kIdentical) {
    error->clear();
    return true;
  }
  uint64_t n = 0;
  if (p->mode == kStandalone) {
    if (!in.Varint(&n) || !in.Bytes(n, &p->verbatim)) {
      return false;
    }
  } else {
    if (!in.Varint(&p->op_count) || !in.Varint(&n) || !in.Bytes(n, &p->ops) ||
        !in.Varint(&n) || !in.Bytes(n, &p->literals)) {
      return false;
    }
  }
  for (const Group& group : p->groups) {
    std::string_view columns;
    if (group.length != 0 && group.slots > UINT64_MAX / group.length) {
      return false;
    }
    if (!in.Bytes(group.length * group.slots, &columns)) {
      return false;
    }
    p->matrices.push_back(columns);
  }
  error->clear();
  return true;
}

// Where every slot of a parsed file lies in its original bytes, with the
// key that pairs it with the same slot of another file of the flow.
struct Slot {
  std::string key;
  uint64_t offset;
  uint64_t length;
};

std::vector<std::vector<Slot>> Slots(const Parsed& p) {
  std::vector<std::vector<Slot>> slots(p.groups.size());
  // A table's instances in the order they appear: the k-th instance of
  // dbInst in one file is the k-th in the next.
  std::map<std::string, std::map<uint64_t, uint64_t>> rank;
  uint64_t pos = 0;
  for (const PlacedRun& run : p.runs) {
    const Group& group = p.groups[run.group];
    auto& ranks = rank[group.table];
    const uint64_t r = ranks.emplace(run.instance, ranks.size()).first->second;
    pos += run.gap;
    for (uint64_t k = 0; k < run.count; ++k) {
      std::string key = group.table;
      key.push_back('\0');
      PutVarint(&key, r);
      PutVarint(&key, run.id + k);
      slots[run.group].push_back(Slot{std::move(key), pos, group.length});
      pos += group.length;
    }
  }
  return slots;
}

// The bytes of `odb` in no slot, in order.
std::string Verbatim(std::string_view odb, const Parsed& p) {
  std::string out;
  uint64_t pos = 0;
  for (const PlacedRun& run : p.runs) {
    out.append(odb.substr(pos, run.gap));
    pos += run.gap + run.count * p.groups[run.group].length;
  }
  out.append(odb.substr(std::min<uint64_t>(pos, odb.size())));
  return out;
}

using SlotMap = std::unordered_map<std::string, std::string_view>;

SlotMap MapSlots(std::string_view odb, const Parsed& p) {
  SlotMap map;
  for (const auto& group : Slots(p)) {
    for (const Slot& slot : group) {
      if (slot.offset + slot.length <= odb.size()) {
        map.emplace(slot.key, odb.substr(slot.offset, slot.length));
      }
    }
  }
  return map;
}

// A slot's difference from its partner, and back: 4-byte fields after
// the allocated flag are subtracted, the flag and any tail are xor-ed.
uint64_t FieldsEnd(uint64_t length) {
  return length < 1 ? 0 : 1 + (length - 1) / 4 * 4;
}

void Subtract(char* slot, const char* base, uint64_t length) {
  const uint64_t end = FieldsEnd(length);
  for (uint64_t o = 1; o < end; o += 4) {
    Store(slot + o, Load(slot + o) - Load(base + o));
  }
  for (uint64_t b = 0; b < length; b = b == 0 ? end : b + 1) {
    slot[b] ^= base[b];
  }
}

void Add(char* slot, const char* base, uint64_t length) {
  const uint64_t end = FieldsEnd(length);
  for (uint64_t o = 1; o < end; o += 4) {
    Store(slot + o, Load(slot + o) + Load(base + o));
  }
  for (uint64_t b = 0; b < length; b = b == 0 ? end : b + 1) {
    slot[b] ^= base[b];
  }
}

// `data` as copies from `base` and literals.
void Diff(std::string_view base, std::string_view data, uint64_t* op_count,
          std::string* ops, std::string* literals) {
  constexpr int kBits = 22;
  constexpr uint64_t kWindow = 8;
  constexpr uint64_t kMinCopy = 16;
  auto hash = [](const char* p) {
    uint64_t v;
    std::memcpy(&v, p, sizeof v);
    return static_cast<size_t>((v * 0x9e3779b97f4a7c15ull) >> (64 - kBits));
  };
  std::vector<uint32_t> table(size_t{1} << kBits, UINT32_MAX);
  for (uint64_t i = 0; i + kWindow <= base.size(); ++i) {
    table[hash(base.data() + i)] = static_cast<uint32_t>(i);
  }
  uint64_t literal_start = 0;
  uint64_t last_copy_end = 0;
  uint64_t i = 0;
  auto emit = [&](uint64_t copy_offset, uint64_t copy_length) {
    PutVarint(ops, i - literal_start);
    literals->append(data.substr(literal_start, i - literal_start));
    PutVarint(ops, copy_length);
    PutVarint(ops, ZigZag(static_cast<int64_t>(copy_offset) -
                          static_cast<int64_t>(last_copy_end)));
    last_copy_end = copy_offset + copy_length;
    ++*op_count;
  };
  while (i + kWindow <= data.size()) {
    const uint32_t c = table[hash(data.data() + i)];
    if (c != UINT32_MAX &&
        std::memcmp(base.data() + c, data.data() + i, kWindow) == 0) {
      uint64_t n = kWindow;
      while (i + n < data.size() && c + n < base.size() &&
             base[c + n] == data[i + n]) {
        ++n;
      }
      if (n >= kMinCopy) {
        emit(c, n);
        i += n;
        literal_start = i;
        continue;
      }
    }
    ++i;
  }
  i = data.size();
  emit(last_copy_end, 0);
}

bool Patch(std::string_view base, const Parsed& p, std::string* out) {
  Reader ops(p.ops);
  uint64_t lit = 0;
  uint64_t last_copy_end = 0;
  for (uint64_t k = 0; k < p.op_count; ++k) {
    uint64_t literal_length = 0;
    uint64_t copy_length = 0;
    uint64_t offset = 0;
    if (!ops.Varint(&literal_length) || !ops.Varint(&copy_length) ||
        !ops.Varint(&offset) || literal_length > p.literals.size() - lit) {
      return false;
    }
    out->append(p.literals.substr(lit, literal_length));
    lit += literal_length;
    const int64_t start =
        static_cast<int64_t>(last_copy_end) + UnZigZag(offset);
    if (start < 0 || static_cast<uint64_t>(start) > base.size() ||
        copy_length > base.size() - start) {
      return false;
    }
    out->append(base.substr(start, copy_length));
    last_copy_end = start + copy_length;
  }
  return lit == p.literals.size();
}

void PutBase(std::string* out, const BaseRef& base) {
  PutVarint(out, base.name.size());
  out->append(base.name);
  PutVarint(out, base.size);
  PutVarint(out, base.hash);
}

// Header, groups and runs, as every form of a file writes them.
void PutStructure(std::string* out, uint64_t mode, uint64_t size,
                  const BaseRef* base, const std::vector<Group>& groups,
                  const std::vector<PlacedRun>& runs, bool predictors) {
  out->clear();
  out->append(kMagic);
  PutVarint(out, kVersion);
  PutVarint(out, size);
  PutVarint(out, mode);
  if (base != nullptr) {
    PutBase(out, *base);
  }
  PutVarint(out, groups.size());
  for (const Group& group : groups) {
    PutVarint(out, group.table.size());
    out->append(group.table);
    PutVarint(out, group.length);
    PutVarint(out, group.slots);
    PutVarint(out, predictors ? group.predictors.size() : 0);
    if (predictors) {
      for (const Predictor& p : group.predictors) {
        PutVarint(out, p.offset);
        PutVarint(out, p.kind);
        PutVarint(out, p.param);
      }
    }
  }
  PutVarint(out, runs.size());
  uint64_t last_instance = 0;
  uint64_t last_end = 0;
  for (const PlacedRun& run : runs) {
    const bool same = run.instance == last_instance;
    PutVarint(out, run.gap);
    PutVarint(out, run.group);
    PutVarint(out, run.count);
    PutVarint(out, run.instance - last_instance);
    PutVarint(out, run.id - (same ? last_end : 0));
    last_instance = run.instance;
    last_end = run.id + run.count;
  }
}

void PutColumns(std::string* out, const std::string& rows, uint64_t length,
                uint64_t slots) {
  const size_t start = out->size();
  out->resize(start + length * slots);
  char* columns = out->data() + start;
  for (uint64_t s = 0; s < slots; ++s) {
    for (uint64_t b = 0; b < length; ++b) {
      columns[b * slots + s] = rows[s * length + b];
    }
  }
}

std::string Rows(std::string_view columns, uint64_t length, uint64_t slots) {
  std::string rows(length * slots, '\0');
  for (uint64_t s = 0; s < slots; ++s) {
    for (uint64_t b = 0; b < length; ++b) {
      rows[s * length + b] = columns[b * slots + s];
    }
  }
  return rows;
}

SlotIds IdsOf(const Parsed& p, size_t g) {
  SlotIds ids;
  for (const PlacedRun& run : p.runs) {
    if (run.group != g) {
      continue;
    }
    for (uint64_t k = 0; k < run.count; ++k) {
      ids.id.push_back(static_cast<uint32_t>(run.id + k));
      ids.instance.push_back(static_cast<uint32_t>(run.instance));
    }
  }
  return ids;
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
      groups.push_back(Group{run.table, run.length, 0, {}});
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

  // Runs as the encoding lists them. A table instance is a stretch of one
  // table's runs with nothing in between; a slot's id is its position in
  // the instance, counting slots of every length. A run that continues
  // the previous one's group, instance and ids is merged into it.
  std::vector<PlacedRun> placed;
  std::vector<std::string> matrix(kept.size());
  std::vector<SlotIds> ids(kept.size());
  for (size_t g = 0; g < kept.size(); ++g) {
    matrix[g].reserve(kept[g].length * kept[g].slots);
    ids[g].id.reserve(kept[g].slots);
    ids[g].instance.reserve(kept[g].slots);
  }
  std::string verbatim;
  uint64_t pos = 0;
  uint64_t instance = 0;
  uint64_t next_id = 0;
  for (size_t r = 0; r < runs.size(); ++r) {
    const Run& run = runs[r];
    if (r == 0 || run.table != runs[r - 1].table ||
        run.offset != runs[r - 1].offset +
                          runs[r - 1].length * runs[r - 1].count) {
      ++instance;
      next_id = 0;
    }
    const uint64_t id = next_id;
    next_id += run.count;
    const size_t g = renumber[run_group[r]];
    if (g == SIZE_MAX) {
      continue;
    }
    const uint64_t gap = run.offset - pos;
    verbatim.append(odb.substr(pos, gap));
    if (gap == 0 && !placed.empty() && placed.back().group == g &&
        placed.back().instance == instance &&
        placed.back().id + placed.back().count == id) {
      placed.back().count += run.count;
    } else {
      placed.push_back(PlacedRun{gap, g, run.count, instance, id});
    }
    matrix[g].append(odb.substr(run.offset, run.length * run.count));
    for (uint64_t k = 0; k < run.count; ++k) {
      ids[g].id.push_back(static_cast<uint32_t>(id + k));
      ids[g].instance.push_back(static_cast<uint32_t>(instance));
    }
    pos = run.offset + run.length * run.count;
  }
  verbatim.append(odb.substr(pos));

  for (size_t g = 0; g < kept.size(); ++g) {
    kept[g].predictors = ApplyPredictors(&matrix[g], kept[g].length, ids[g]);
  }

  PutStructure(out, kStandalone, odb.size(), nullptr, kept, placed, true);
  PutVarint(out, verbatim.size());
  out->append(verbatim);
  for (size_t g = 0; g < kept.size(); ++g) {
    PutColumns(out, matrix[g], kept[g].length, kept[g].slots);
  }
  return true;
}

bool EncodeDelta(std::string_view encoded, std::string_view odb,
                 const std::string& base_name, std::string_view base_encoded,
                 std::string_view base_odb, std::string* out,
                 std::string* error) {
  Parsed file;
  Parsed base;
  if (!ParseContainer(encoded, &file, error) ||
      !ParseContainer(base_encoded, &base, error)) {
    return false;
  }
  if (file.size != odb.size() || base.size != base_odb.size()) {
    *error = "sizes do not match the encoded files";
    return false;
  }
  const BaseRef ref{base_name, base_odb.size(), Hash(base_odb)};
  if (odb == base_odb) {
    PutStructure(out, kIdentical, odb.size(), &ref, file.groups, file.runs,
                 false);
    return true;
  }
  const SlotMap partners = MapSlots(base_odb, base);
  const std::vector<std::vector<Slot>> slots = Slots(file);
  PutStructure(out, kDelta, odb.size(), &ref, file.groups, file.runs, false);
  uint64_t op_count = 0;
  std::string ops;
  std::string literals;
  Diff(Verbatim(base_odb, base), Verbatim(odb, file), &op_count, &ops,
       &literals);
  PutVarint(out, op_count);
  PutVarint(out, ops.size());
  out->append(ops);
  PutVarint(out, literals.size());
  out->append(literals);
  for (size_t g = 0; g < file.groups.size(); ++g) {
    const uint64_t length = file.groups[g].length;
    std::string rows;
    rows.reserve(length * slots[g].size());
    for (const Slot& slot : slots[g]) {
      const size_t at = rows.size();
      rows.append(odb.substr(slot.offset, slot.length));
      const auto it = partners.find(slot.key);
      if (it != partners.end() && it->second.size() == length) {
        Subtract(rows.data() + at, it->second.data(), length);
      }
    }
    PutColumns(out, rows, length, slots[g].size());
  }
  return true;
}

bool BaseOf(std::string_view encoded, std::string* name, std::string* error) {
  Parsed p;
  if (!ParseContainer(encoded, &p, error)) {
    return false;
  }
  *name = p.mode == kStandalone ? "" : p.base.name;
  return true;
}

bool Decode(std::string_view encoded, const ResolveBase& resolve,
            std::string* out, std::string* error) {
  Parsed p;
  if (!ParseContainer(encoded, &p, error)) {
    return false;
  }
  // The file's own columns back to rows first: a caller fetches the base
  // meanwhile.
  std::vector<std::string> rows;
  for (size_t g = 0; g < p.matrices.size(); ++g) {
    rows.push_back(
        Rows(p.matrices[g], p.groups[g].length, p.groups[g].slots));
    if (p.mode == kStandalone &&
        !UndoPredictors(p.groups[g].predictors, &rows[g], p.groups[g].length,
                        IdsOf(p, g))) {
      *error = "truncated or corrupt encoded .odb";
      return false;
    }
  }
  std::string base_encoded;
  std::string base_odb;
  Parsed base;
  std::string verbatim_storage;
  std::string_view verbatim = p.verbatim;
  if (p.mode != kStandalone) {
    if (!resolve || !resolve(p.base.name, &base_encoded, &base_odb, error)) {
      if (error->empty()) {
        *error = "base " + p.base.name + " is not available";
      }
      return false;
    }
    if (base_odb.size() != p.base.size || Hash(base_odb) != p.base.hash) {
      *error = "base " + p.base.name + " is not the file this was encoded "
               "against";
      return false;
    }
    if (p.mode == kIdentical) {
      *out = std::move(base_odb);
      error->clear();
      return true;
    }
    if (!ParseContainer(base_encoded, &base, error)) {
      *error = "base " + p.base.name + ": " + *error;
      return false;
    }
    if (!Patch(Verbatim(base_odb, base), p, &verbatim_storage)) {
      *error = "truncated or corrupt encoded .odb";
      return false;
    }
    verbatim = verbatim_storage;
    const SlotMap partners = MapSlots(base_odb, base);
    const std::vector<std::vector<Slot>> slots = Slots(p);
    for (size_t g = 0; g < rows.size(); ++g) {
      const uint64_t length = p.groups[g].length;
      for (size_t s = 0; s < slots[g].size(); ++s) {
        const auto it = partners.find(slots[g][s].key);
        if (it != partners.end() && it->second.size() == length) {
          Add(rows[g].data() + s * length, it->second.data(), length);
        }
      }
    }
  }

  out->clear();
  out->reserve(p.size);
  std::vector<uint64_t> taken(p.groups.size(), 0);
  size_t vpos = 0;
  for (const PlacedRun& run : p.runs) {
    const Group& group = p.groups[run.group];
    if (run.gap > verbatim.size() - vpos) {
      *error = "truncated or corrupt encoded .odb";
      return false;
    }
    out->append(verbatim.substr(vpos, run.gap));
    vpos += run.gap;
    out->append(rows[run.group], taken[run.group] * group.length,
                run.count * group.length);
    taken[run.group] += run.count;
  }
  out->append(verbatim.substr(vpos));
  if (out->size() != p.size) {
    *error = "truncated or corrupt encoded .odb";
    return false;
  }
  error->clear();
  return true;
}

}  // namespace odb_codec
