#pragma once

#include "loader_impl.hpp"
#include <vector>
#include <string>

struct Database {
    std::vector<int64_t> t_tripkey;
    std::vector<std::string> t_pickuploc;
    std::vector<int64_t> t_pickuptime;
};

Database* build(ParquetTables* tables);
