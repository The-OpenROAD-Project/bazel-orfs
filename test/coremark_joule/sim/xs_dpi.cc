// The DPI functions XiangShan's simulation memory calls.
//
// device.AXI4Memory keeps the AXI protocol in RTL and puts the array and
// the timing behind four DPI calls. Implementing them here rather than
// linking difftest's ram.cpp keeps the harness to what this study needs:
// difftest's runtime brings a NEMU reference model and a great deal else,
// and correctness here is CoreMark's own CRCs read from stdout.
//
// The contract, read off the generated Verilog:
//
//   longint difftest_ram_read(longint rIdx)
//   void    difftest_ram_write(longint index, longint data, longint mask)
//   bit     memory_request(longint address, int id, bit isWrite)
//   longint memory_response(bit isWrite)
//
// Indices are 64-bit words relative to the memory's own base address:
// AXI4MemoryImp subtracts ramBaseAddr before it forms them, so offset
// zero here is 0x8000_0000 to the program.
//
// SPDX-License-Identifier: Apache-2.0

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <string>
#include <vector>

namespace {

// 256 MiB, matching the AddressSet the generator gives AXI4Memory.
// CoreMark's image is a megabyte; the rest is never touched, and a
// std::vector of zeros costs nothing until it is.
constexpr uint64_t kMemBytes = 256ull * 1024 * 1024;

std::vector<uint8_t> &memory()
{
    static std::vector<uint8_t> *mem = new std::vector<uint8_t>(kMemBytes, 0);
    return *mem;
}

// Requests accepted but not yet responded to, oldest first. The model has
// no latency: a request is accepted the cycle it is offered and its
// response is available the next time the RTL asks. That is deliberate --
// everything past L1 is outside the measurement boundary, so the memory
// system this study reports is the one on the core's side of it -- and it
// makes CoreMark/MHz an upper bound against a real DRAM, which is worth
// stating rather than hiding.
std::deque<uint32_t> &pending(bool is_write)
{
    static std::deque<uint32_t> reads;
    static std::deque<uint32_t> writes;
    return is_write ? writes : reads;
}

// The image is loaded once, on the first access, from the same +meminit=
// plusarg the other three cores' RTL wrappers read with $readmemh. One
// 32-bit word per line, lowest address first, which is what elf2hex.py
// emits.
void load_image_once()
{
    static bool done = false;
    if (done) {
        return;
    }
    done = true;

    const char *path = nullptr;
    // Verilated::commandArgs has the plusargs, but reaching them from a
    // plain DPI function means depending on the Verilated runtime here.
    // The harness re-exports the value instead.
    path = getenv("CMJ_MEMINIT");
    if (path == nullptr) {
        fprintf(stderr, "xs_dpi: CMJ_MEMINIT is not set; memory is zero\n");
        return;
    }

    FILE *f = fopen(path, "r");
    if (f == nullptr) {
        fprintf(stderr, "xs_dpi: cannot read %s\n", path);
        exit(1);
    }

    std::vector<uint8_t> &mem = memory();
    uint64_t offset = 0;
    char line[64];
    while (fgets(line, sizeof(line), f) != nullptr) {
        if (line[0] == '\0' || line[0] == '\n') {
            continue;
        }
        const uint32_t word = static_cast<uint32_t>(strtoul(line, nullptr, 16));
        if (offset + 4 > mem.size()) {
            fprintf(stderr, "xs_dpi: %s is larger than the %llu MiB memory\n", path,
                    static_cast<unsigned long long>(kMemBytes >> 20));
            exit(1);
        }
        memcpy(&mem[offset], &word, 4);
        offset += 4;
    }
    fclose(f);
}

}  // namespace

extern "C" {

int64_t difftest_ram_read(int64_t rIdx)
{
    load_image_once();
    const uint64_t offset = static_cast<uint64_t>(rIdx) * 8;
    std::vector<uint8_t> &mem = memory();
    if (offset + 8 > mem.size()) {
        // The core may speculate outside the mapped range; AXI4Memory's
        // own comment says to let the helper deal with it.
        return 0;
    }
    int64_t value = 0;
    memcpy(&value, &mem[offset], 8);
    return value;
}

void difftest_ram_write(int64_t index, int64_t data, int64_t mask)
{
    load_image_once();
    const uint64_t offset = static_cast<uint64_t>(index) * 8;
    std::vector<uint8_t> &mem = memory();
    if (offset + 8 > mem.size()) {
        return;
    }
    uint64_t old = 0;
    memcpy(&old, &mem[offset], 8);
    const uint64_t m = static_cast<uint64_t>(mask);
    const uint64_t merged = (old & ~m) | (static_cast<uint64_t>(data) & m);
    memcpy(&mem[offset], &merged, 8);
}

// Returns whether the request was accepted. Always, here: the queue is
// unbounded and the model has no latency.
unsigned char memory_request(int64_t address, int32_t id, unsigned char isWrite)
{
    (void)address;
    pending(isWrite != 0).push_back(static_cast<uint32_t>(id));
    return 1;
}

// Bit 32 is validity, bits 31:0 are the id of a completed request. Called
// only when the RTL has room for a response, so popping here is what the
// helper's `enable` means.
int64_t memory_response(unsigned char isWrite)
{
    std::deque<uint32_t> &queue = pending(isWrite != 0);
    if (queue.empty()) {
        return 0;
    }
    const uint64_t id = queue.front();
    queue.pop_front();
    return static_cast<int64_t>((1ull << 32) | id);
}

}  // extern "C"
