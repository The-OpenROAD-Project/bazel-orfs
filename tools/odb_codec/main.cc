// odb_codec: the ODB_CODEC OpenROAD's read_db and write_db run, and the
// delta encoding of a stage's substeps. See odb_codec.h.
#include <fcntl.h>
#include <spawn.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "odb_codec.h"

extern char** environ;

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

// Replaces path by bytes, all at once, so that a process reading it sees
// the old file or the new one.
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

std::string Dir(const std::string& path) {
  const size_t slash = path.rfind('/');
  return slash == std::string::npos ? "" : path.substr(0, slash + 1);
}

std::string Base(const std::string& path) {
  const size_t slash = path.rfind('/');
  return slash == std::string::npos ? path : path.substr(slash + 1);
}

std::string Self() {
  char buf[PATH_MAX];
  const ssize_t n = readlink("/proc/self/exe", buf, sizeof buf - 1);
  return n > 0 ? std::string(buf, n) : "odb_codec";
}

pid_t Spawn(const std::vector<std::string>& args, int out_fd) {
  std::vector<char*> argv;
  for (const std::string& arg : args) {
    argv.push_back(const_cast<char*>(arg.c_str()));
  }
  argv.push_back(nullptr);
  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  if (out_fd >= 0) {
    posix_spawn_file_actions_adddup2(&actions, out_fd, STDOUT_FILENO);
  }
  pid_t pid = -1;
  const int error =
      posix_spawn(&pid, argv[0], &actions, nullptr, argv.data(), environ);
  posix_spawn_file_actions_destroy(&actions);
  return error == 0 ? pid : -1;
}

int Wait(pid_t pid) {
  int status = 0;
  while (waitpid(pid, &status, 0) < 0) {
    if (errno != EINTR) {
      return 1;
    }
  }
  return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}

// A base being decoded by a child process, read on a thread, so that the
// caller decodes its own file meanwhile. A chain of deltas is a pipeline
// of these, every file of it decoding at once.
class BaseFetch {
 public:
  explicit BaseFetch(std::string path) : path_(std::move(path)) {
    int fds[2];
    if (pipe2(fds, O_CLOEXEC) != 0) {
      return;
    }
    pid_ = Spawn({Self(), "decode", path_}, fds[1]);
    close(fds[1]);
    if (pid_ < 0) {
      close(fds[0]);
      return;
    }
    reader_ = std::thread([this, fd = fds[0]] {
      char buf[1 << 16];
      ssize_t n;
      while ((n = read(fd, buf, sizeof buf)) > 0 || (n < 0 && errno == EINTR)) {
        if (n > 0) {
          odb_.append(buf, n);
        }
      }
      close(fd);
    });
  }

  ~BaseFetch() { Finish(); }

  // The base's encoded bytes and original bytes.
  bool Get(std::string* encoded, std::string* odb, std::string* error) {
    const int status = Finish();
    if (pid_ < 0 || status != 0) {
      *error = "cannot decode base " + path_;
      return false;
    }
    if (!ReadFile(path_, encoded)) {
      *error = "cannot read base " + path_;
      return false;
    }
    *odb = std::move(odb_);
    return true;
  }

 private:
  int Finish() {
    if (reader_.joinable()) {
      reader_.join();
      status_ = Wait(pid_);
    }
    return status_;
  }

  std::string path_;
  pid_t pid_ = -1;
  int status_ = 1;
  std::thread reader_;
  std::string odb_;
};

// The original bytes of any .odb, encoded or not, with its base fetched
// from next to it.
bool Original(const std::string& path, const std::string& bytes,
              std::string* odb, std::string* error) {
  if (!odb_codec::IsEncoded(bytes)) {
    *odb = bytes;
    return true;
  }
  std::string base;
  if (!odb_codec::BaseOf(bytes, &base, error)) {
    return false;
  }
  std::unique_ptr<BaseFetch> fetch;
  if (!base.empty()) {
    fetch = std::make_unique<BaseFetch>(Dir(path) + base);
  }
  return odb_codec::Decode(
      bytes,
      [&](const std::string&, std::string* e, std::string* o, std::string* err) {
        return fetch && fetch->Get(e, o, err);
      },
      odb, error);
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
  if (!odb_codec::Decode(encoded, nullptr, &decoded, &error) ||
      decoded != odb) {
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

// Re-encodes an encoded file as a delta against `base`, a file next to
// it. As with encode, a file that cannot be is left as it is.
int Delta(const std::string& path, const std::string& base_path) {
  if (Dir(path) != Dir(base_path)) {
    std::cerr << "odb_codec: " << base_path << " is not next to " << path
              << "\n";
    return 1;
  }
  BaseFetch fetch(base_path);
  std::string encoded;
  std::string odb;
  std::string error;
  if (!ReadFile(path, &encoded)) {
    std::cerr << "odb_codec: cannot read " << path << "\n";
    return 1;
  }
  if (!odb_codec::IsEncoded(encoded)) {
    // A substep the flow skipped is an empty placeholder: nothing to do.
    std::cerr << "odb_codec: " << path << " left as it is: not encoded\n";
    return 0;
  }
  if (!Original(path, encoded, &odb, &error)) {
    std::cerr << "odb_codec: " << path << ": " << error << "\n";
    return 1;
  }
  std::string base_encoded;
  std::string base_odb;
  if (!fetch.Get(&base_encoded, &base_odb, &error)) {
    std::cerr << "odb_codec: " << path << ": " << error << "\n";
    return 1;
  }
  std::string delta;
  const std::string name = Base(base_path);
  if (!odb_codec::EncodeDelta(encoded, odb, name, base_encoded, base_odb,
                              &delta, &error)) {
    std::cerr << "odb_codec: " << path << " left as it was: " << error
              << "\n";
    return 0;
  }
  std::string decoded;
  auto same_base = [&](const std::string&, std::string* e, std::string* o,
                       std::string*) {
    *e = base_encoded;
    *o = base_odb;
    return true;
  };
  if (!odb_codec::Decode(delta, same_base, &decoded, &error) ||
      decoded != odb) {
    std::cerr << "odb_codec: " << path
              << " left as it was: delta did not round-trip\n";
    return 0;
  }
  if (!WriteFile(path, delta)) {
    std::cerr << "odb_codec: cannot write " << path << "\n";
    return 1;
  }
  return 0;
}

// A stage's substeps as a chain ending in its output: each file a delta
// against the next, all of them at once, one process each.
int Chain(const std::vector<std::string>& files) {
  std::vector<pid_t> pids;
  for (size_t i = 0; i + 1 < files.size(); ++i) {
    pids.push_back(Spawn({Self(), "delta", files[i], files[i + 1]}, -1));
  }
  int status = 0;
  for (const pid_t pid : pids) {
    const int s = pid < 0 ? 1 : Wait(pid);
    status = status != 0 ? status : s;
  }
  return status;
}

// Writes the .odb to stdout: decoded when encoded, otherwise as it is.
int Decode(const std::string& path) {
  std::string bytes;
  std::string odb;
  std::string error;
  if (!ReadFile(path, &bytes)) {
    std::cerr << "odb_codec: cannot read " << path << "\n";
    return 1;
  }
  if (!Original(path, bytes, &odb, &error)) {
    std::cerr << "odb_codec: " << path << ": " << error << "\n";
    return 1;
  }
  if (std::fwrite(odb.data(), 1, odb.size(), stdout) != odb.size() ||
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
  if (verb == "delta" && argc == 4) {
    return Delta(argv[2], argv[3]);
  }
  if (verb == "base" && argc == 3) {
    std::string bytes;
    std::string name;
    std::string error;
    if (!ReadFile(argv[2], &bytes)) {
      std::cerr << "odb_codec: cannot read " << argv[2] << "\n";
      return 1;
    }
    if (odb_codec::IsEncoded(bytes) &&
        !odb_codec::BaseOf(bytes, &name, &error)) {
      std::cerr << "odb_codec: " << argv[2] << ": " << error << "\n";
      return 1;
    }
    std::cout << name << "\n";
    return 0;
  }
  if (verb == "chain" && argc >= 4) {
    return Chain(std::vector<std::string>(argv + 2, argv + argc));
  }
  std::cerr
      << "usage: odb_codec encode FILE LAYOUT   reformat FILE in place\n"
         "       odb_codec decode FILE          the .odb, on stdout\n"
         "       odb_codec delta FILE BASE      FILE as a delta against "
         "BASE, next to it\n"
         "       odb_codec chain F1 ... Fn      each Fi a delta against "
         "Fi+1, in parallel\n"
         "       odb_codec base FILE            the file FILE is stored "
         "against, if any\n";
  return 2;
}
