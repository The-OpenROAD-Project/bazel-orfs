// Hermetically recompresses a single-member .7z archive into a deterministic
// .gz stream (no embedded mtime) using BCR's libarchive.

#include <archive.h>
#include <archive_entry.h>

#include <cstdio>
#include <cstdlib>

namespace {

[[noreturn]] void die(const char* step, struct archive* a) {
  std::fprintf(stderr, "un7z_gz: %s: %s\n", step,
               a ? archive_error_string(a) : "failed");
  std::exit(1);
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s <input.7z> <output.gz>\n", argv[0]);
    return 2;
  }

  struct archive* in = archive_read_new();
  if (!in) die("archive_read_new", nullptr);
  if (archive_read_support_format_7zip(in) != ARCHIVE_OK) {
    die("archive_read_support_format_7zip", in);
  }
  if (archive_read_open_filename(in, argv[1], 1 << 16) != ARCHIVE_OK) {
    die("archive_read_open_filename", in);
  }

  struct archive_entry* in_entry = nullptr;
  int r = archive_read_next_header(in, &in_entry);
  if (r != ARCHIVE_OK) {
    die("archive_read_next_header", in);
  }

  struct archive* out = archive_write_new();
  if (!out) die("archive_write_new", nullptr);
  if (archive_write_add_filter_gzip(out) != ARCHIVE_OK) {
    die("archive_write_add_filter_gzip", out);
  }
  if (archive_write_set_format_raw(out) != ARCHIVE_OK) {
    die("archive_write_set_format_raw", out);
  }
  if (archive_write_set_options(out, "gzip:!timestamp") != ARCHIVE_OK) {
    die("archive_write_set_options", out);
  }
  if (archive_write_open_filename(out, argv[2]) != ARCHIVE_OK) {
    die("archive_write_open_filename", out);
  }

  struct archive_entry* out_entry = archive_entry_new();
  archive_entry_set_filetype(out_entry, AE_IFREG);
  if (archive_write_header(out, out_entry) != ARCHIVE_OK) {
    die("archive_write_header", out);
  }
  archive_entry_free(out_entry);

  const void* buff = nullptr;
  size_t size = 0;
  la_int64_t offset = 0;
  while (true) {
    r = archive_read_data_block(in, &buff, &size, &offset);
    if (r == ARCHIVE_EOF) break;
    if (r != ARCHIVE_OK) die("archive_read_data_block", in);
    if (size > 0) {
      la_ssize_t written = archive_write_data(out, buff, size);
      if (written < 0 || static_cast<size_t>(written) != size) {
        die("archive_write_data", out);
      }
    }
  }

  struct archive_entry* extra = nullptr;
  if (archive_read_next_header(in, &extra) != ARCHIVE_EOF) {
    std::fprintf(stderr, "un7z_gz: expected exactly 1 entry in %s\n", argv[1]);
    return 1;
  }

  if (archive_write_close(out) != ARCHIVE_OK) die("archive_write_close", out);
  archive_write_free(out);
  if (archive_read_close(in) != ARCHIVE_OK) die("archive_read_close", in);
  archive_read_free(in);
  return 0;
}
