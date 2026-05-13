#include "builder_impl.hpp"
#include <thread>
#include <vector>
#include <arrow/api.h>
#include <algorithm>

Database* build(ParquetTables* tables) {
    auto db = new Database();
    auto table = tables->trip;
    if (!table) return db;

    auto tripkey_col = table->GetColumnByName("t_tripkey");
    auto pickuploc_col = table->GetColumnByName("t_pickuploc");
    auto pickuptime_col = table->GetColumnByName("t_pickuptime");

    if (!tripkey_col || !pickuploc_col || !pickuptime_col) return db;

    size_t num_rows = table->num_rows();
    db->t_tripkey.resize(num_rows);
    db->t_pickuptime.resize(num_rows);
    // Note: Assuming t_pickuploc is binary/WKB, storing as string for simplicity
    db->t_pickuploc.resize(num_rows);

    auto load_tripkey = [&](std::vector<int64_t>& vec) {
        int64_t offset = 0;
        for (const auto& chunk : tripkey_col->chunks()) {
            auto arr = std::static_pointer_cast<arrow::Int64Array>(chunk);
            std::copy(arr->raw_values(), arr->raw_values() + arr->length(), vec.begin() + offset);
            offset += arr->length();
        }
    };

    auto load_pickuptime = [&](std::vector<int64_t>& vec) {
        int64_t offset = 0;
        for (const auto& chunk : pickuptime_col->chunks()) {
            auto arr = std::static_pointer_cast<arrow::Int64Array>(chunk);
            std::copy(arr->raw_values(), arr->raw_values() + arr->length(), vec.begin() + offset);
            offset += arr->length();
        }
    };

    // Simplified loading for binary column
    auto load_pickuploc = [&](std::vector<std::string>& vec) {
        int64_t offset = 0;
        for (const auto& chunk : pickuploc_col->chunks()) {
            auto arr = std::static_pointer_cast<arrow::BinaryArray>(chunk);
            for (int i = 0; i < arr->length(); ++i) {
                vec[offset + i] = arr->GetString(i);
            }
            offset += arr->length();
        }
    };

    std::thread t1(load_tripkey, std::ref(db->t_tripkey));
    std::thread t2(load_pickuptime, std::ref(db->t_pickuptime));
    std::thread t3(load_pickuploc, std::ref(db->t_pickuploc));
    t1.join();
    t2.join();
    t3.join();

    return db;
}
