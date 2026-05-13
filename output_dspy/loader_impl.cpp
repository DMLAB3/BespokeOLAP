#include "loader_impl.hpp"

#include "loader_utils.hpp"

#include <stdio.h>
#include <unistd.h>


ParquetTables* load(std::string path) {
    auto tables = new ParquetTables{};

    tables->building = ReadParquetTable(path + "building.parquet");
    tables->customer = ReadParquetTable(path + "customer.parquet");
    tables->driver = ReadParquetTable(path + "driver.parquet");
    tables->trip = ReadParquetTable(path + "trip.parquet");
    tables->vehicle = ReadParquetTable(path + "vehicle.parquet");
    tables->zone = ReadParquetTable(path + "zone.parquet");

    return tables;
}
