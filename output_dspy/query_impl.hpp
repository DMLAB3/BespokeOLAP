#pragma once

#include "builder_impl.hpp"
#include "args_parser.hpp"

void execute_queries(Database* db, const std::vector<QueryRequest>& requests);
void run_query2(Database* db);
