#pragma once

#include <string>
#include <vector>
#include <sstream>

struct QueryRequest {
    std::string id;
    std::string params;
};

inline std::vector<QueryRequest> parse_queries(const std::string& input) {
    std::vector<QueryRequest> requests;
    std::stringstream ss(input);
    std::string line;
    while (std::getline(ss, line)) {
        if (line.empty()) continue;
        std::stringstream line_ss(line);
        QueryRequest req;
        line_ss >> req.id;
        std::getline(line_ss, req.params);
        requests.push_back(req);
    }
    return requests;
}
