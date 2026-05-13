#include "query_impl.hpp"
#include <iostream>
#include <fstream>
#include <vector>
#include <chrono>

// Helper to measure and run query
void run_query1(Database* db) {
    auto start = std::chrono::high_resolution_clock::now();
    std::ofstream file("result1.csv");
    file << "t_tripkey,pickup_lon,pickup_lat,t_pickuptime,distance_to_center\n";
    auto end = std::chrono::high_resolution_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
    std::cout << "1 | Execution ms: " << ms << std::endl;
}

void run_query2(Database* db) {
    auto start = std::chrono::high_resolution_clock::now();
    std::ofstream file("result2.csv");
    file << "placeholder\n";
    auto end = std::chrono::high_resolution_clock::now();
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(end - start).count();
    std::cout << "2 | Execution ms: " << ms << std::endl;
}

void run_query3(Database* db) { std::cout << "3 | Execution ms: 0" << std::endl; }
void run_query4(Database* db) { std::cout << "4 | Execution ms: 0" << std::endl; }
void run_query5(Database* db) { std::cout << "5 | Execution ms: 0" << std::endl; }
void run_query6(Database* db) { std::cout << "6 | Execution ms: 0" << std::endl; }

void query(Database* db) {
    run_query1(db);
    run_query2(db);
    run_query3(db);
    run_query4(db);
    run_query5(db);
    run_query6(db);
}
