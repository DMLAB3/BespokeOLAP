#include "query_impl.hpp"
#include "query1_impl.hpp"
#include <iostream>
#include <chrono>
#include <fstream>
#include <string>

void run_query1(Database* db, const QueryRequest& req) {
    std::ofstream file("result1.csv");
    file << "id,val\n";
}

void execute_queries(Database* db, const std::vector<QueryRequest>& requests) {
    for (const auto& req : requests) {
        auto start = std::chrono::high_resolution_clock::now();
        if (req.id == "1") {
            run_query1(db, req);
        } else {
            // Placeholder for other queries
        }
        auto end = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
        std::cout << req.id << " | Execution ms: " << duration << std::endl;
    }
}

void query(Database* db) {
    std::vector<QueryRequest> requests;
    std::ifstream file("queries.txt");
    std::string line;
    int id = 1;
    while (std::getline(file, line)) {
        if (!line.empty()) {
            requests.push_back({std::to_string(id++), line});
        }
    }
    execute_queries(db, requests);
}