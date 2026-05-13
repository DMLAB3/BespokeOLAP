#pragma once
#include <arrow/table.h>
#include <memory>

struct ParquetTables {
    std::shared_ptr<arrow::Table> building;
    std::shared_ptr<arrow::Table> customer;
    std::shared_ptr<arrow::Table> driver;
    std::shared_ptr<arrow::Table> trip;
    std::shared_ptr<arrow::Table> vehicle;
    std::shared_ptr<arrow::Table> zone;
};
