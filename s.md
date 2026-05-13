# TPC-H
uv run  run_gen_storage_plan.py \
    --conv storageplan1-22v1 \
    --benchmark tpch \
    --auto_u --auto_finish


uv run run_gen_storage_plan.py \
    --conv storageplan1-22v1 \
    --benchmark spatial 

/mnt/labstore/bespoke_olap/conversations/spatial_storageplan1-22v1.json'


git fetch cache_repo refs/snapshots/*:refs/snapshots/*



uv run run_gen_storage_plan.py   --conv storageplan1v2     --benchmark spatial --disable_repo_sync


# Spatial
uv run run_gen_base_impl.py     --conv basef1-12v1    --benchmark spatial 

    --auto_u --auto_finish



find . \( -type d \( -name ".venv" -o -name "output"  \) -prune \) -o -type f -name "*.py" -print