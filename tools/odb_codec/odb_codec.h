// odb_codec: reformats an OpenROAD .odb so that it compresses better, and
// restores it byte for byte. It knows nothing of the .odb schema: where
// the table slots lie comes from the layout OpenROAD's write_db writes
// next to the file when ODB_CODEC is set. An encoded file carries
// everything decoding needs, except, for a delta, its base: another
// encoded .odb in the same directory, named in the file and checked by
// size and hash.
#pragma once

#include <functional>
#include <string>
#include <string_view>

namespace odb_codec {

// Reformats `odb` with `layout`. Returns false, with `error` set, when the
// layout does not describe `odb`.
bool Encode(std::string_view odb, std::string_view layout, std::string* out,
            std::string* error);

// Re-encodes a file as a delta against `base_name`, whose encoded bytes
// and original bytes are given. `encoded` is the file in any encoded form,
// `odb` its original bytes. A file identical to its base is stored as
// just that.
bool EncodeDelta(std::string_view encoded, std::string_view odb,
                 const std::string& base_name, std::string_view base_encoded,
                 std::string_view base_odb, std::string* out,
                 std::string* error);

// Whether `bytes` came out of Encode or EncodeDelta.
bool IsEncoded(std::string_view bytes);

// The base an encoded file needs, "" for none.
bool BaseOf(std::string_view encoded, std::string* name, std::string* error);

// Fetches a base by name: its encoded bytes and its original bytes.
using ResolveBase =
    std::function<bool(const std::string& name, std::string* encoded,
                       std::string* odb, std::string* error)>;

// Restores the original bytes. `resolve` is called, at most once and only
// for a delta, after the file's own columns are back in rows, so that a
// caller can be fetching the base meanwhile.
bool Decode(std::string_view encoded, const ResolveBase& resolve,
            std::string* out, std::string* error);

}  // namespace odb_codec
