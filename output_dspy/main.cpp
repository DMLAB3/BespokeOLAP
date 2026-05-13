#include "builder_impl.hpp"
#include "loader_impl.hpp"
#include <iostream>

int main() {
    ParquetTables* tables = load("data/"); // Assuming path
    if (tables && tables->trip) {
        auto table = tables->trip;
        for (int i = 0; i < table->num_columns(); ++i) {
            std::cout << "Column " << i << " name: " << table->schema()->field(i)->name() << " type: " << table->schema()->field(i)->type()->ToString() << std::endl;
        }
    }
    return 0;
}
