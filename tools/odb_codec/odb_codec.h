// odb_codec: reformats an OpenROAD .odb so that it compresses better, and
// restores it byte for byte. It knows nothing of the .odb schema: where
// the table slots lie comes from the layout OpenROAD's write_db writes
// next to the file when ODB_CODEC is set. The reformatted file carries
// everything decoding needs, so any build of the codec reads what any
// other wrote, whatever OpenROAD wrote the .odb.
#pragma once

#include <string>
#include <string_view>

namespace odb_codec {

// Reformats `odb` with `layout`. Returns false, with `error` set, when the
// layout does not describe `odb`.
bool Encode(std::string_view odb, std::string_view layout, std::string* out,
            std::string* error);

// Whether `bytes` came out of Encode.
bool IsEncoded(std::string_view bytes);

// Restores what Encode was handed. Returns false, with `error` set, when
// `encoded` is not a whole Encode output.
bool Decode(std::string_view encoded, std::string* out, std::string* error);

}  // namespace odb_codec
