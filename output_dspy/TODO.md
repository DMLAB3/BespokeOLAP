# Implementation Plan for Specialized Database Engine

- [ ] Check input parquet schemas.
- [ ] Design `Database` struct in `builder_impl.hpp` (SoA layout for performance).
- [ ] Implement `builder_impl.cpp` to load ArrowTables into the `Database` struct.
- [ ] Implement query execution logic in `query_impl.cpp`.
- [ ] Integrate `args_parser.hpp` for parsing query parameters.
- [ ] Implement CSV result writer for `result<RUN_NR>.csv`.
- [ ] Compile the project and verify against `queries.txt`.

## Conceptual Notes
- The database will use an in-memory Struct-of-Arrays (SoA) to maximize cache locality.
- Queries are predefined, allowing us to hard-code specialized scan and join logic for performance.
