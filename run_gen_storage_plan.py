import argparse
import json
import os
import sys
from pathlib import Path

from runtime.orchestrator.runner import run_conv_wrapper
from runtime.services import prepare_storage_plan_run

# add parent to path
sys.path.append(os.path.join(os.getcwd(), ".."))
from dataset.dataset_tables_dict import get_benchmark_schema
from utils.cli_config import add_common_args


def main(args):
    prepared = prepare_storage_plan_run(args)
    benchmark = prepared.benchmark
    short_name = prepared.short_name
    config = prepared.config

    # create conversation
    create_conversation(
        benchmark,
        short_name,
        schema=get_benchmark_schema(benchmark),
        conversation_dir=Path(config.artifacts_dir) / "conversations",
    )

    # run conversation
    run_conv_wrapper(config)


def create_conversation(
    benchmark,
    short_name,
    schema: str,
    conversation_dir: Path,
):
    prompt_list = []

    # parquet engine
    queries_path = "queries.txt"
    spatial_hint = ""
    if benchmark == "spatial":
        spatial_hint = """
SpatialBench geometry columns are stored as parquet binary/WKB payloads and decoded with `ST_GeomFromWKB` in the queries. For spatial tables, consider geometry-aware layouts such as bounding boxes, centroid arrays, compact WKB payload storage, zone/building spatial partitions, and candidate-pruning indexes, while still preserving enough data to reconstruct the original parquet rows.
"""

    prompt_list.append(
        f"""Your task is to analyze the workload and produce a creative in-memory storage-layout summary for the tables accessed by the query. You have the flexibility to return detailed, free-form text that explores not only conventional storage-layout recommendations but also unconventional, novel, and even 'crazy' storage designs. 
You are encouraged to include additional ideas, new partitioning strategies, speculative encoding techniques, or experimental ways of grouping and organizing columns or data. 
For each accessed table, feel free to be inventive and elaborate on possibilities such as hybrid layouts, speculative SoA/AoS (Array of Structures/Structure of Arrays) approaches, novel column encodings, or adaptive partitioning.
Use this as an opportunity to push beyond current norms and propose storage techniques that might be futuristic or outlandish. 
Output the storage layout for each table. Output only the final storage layout.
{spatial_hint}

Important:
- store all the data, and store them in a way that it could be flattened back to the original data
- do not store data redundantly, but you can use compression or encoding, meta data, or special datastructures
- optimized for in-memory (single-node) analytical query processing
    
The queries are listed in the file: {queries_path}.
The schema is:
{schema}

Based on the given queries and schema, provide a detailed and creative storage layout summary for the tables accessed by the query. Feel free to explore unconventional and novel storage designs, including speculative encoding techniques or experimental ways of organizing data. Write it to the file: `storage_plan.txt`."""
    )

    target_path = conversation_dir / f"{benchmark}_{short_name}.json"

    if os.path.exists(target_path):
        raise ValueError(f"Conversation file {target_path} already exists.")

    with open(target_path, "w") as f:
        json.dump(prompt_list, f, indent=2)


def build_parser(*, add_help: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=add_help)
    parser.add_argument(
        "--conv",
        type=str,
        required=True,
        help="Short name for the conversation",
    )

    add_common_args(
        parser,
        include_notify=True,
        include_replay_cache=True,
        include_benchmark=True,
        include_model=True,
        include_disable_wandb=True,
        include_disable_tracing=True,
        include_auto_u=True,
        include_auto_finish=True,
        include_replay=True,
        include_only_from_llm_cache=True,
        include_artifacts_dir=True,
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    main(args)
