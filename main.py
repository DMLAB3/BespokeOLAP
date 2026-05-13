import argparse
from runtime.orchestrator.runner import run_conv_wrapper
from utils.cli_config import add_common_args
from utils.pkgconfig import check_pkg


if __name__ == "__main__":
    if not check_pkg("arrow", "parquet"):
        raise Exception(
            "Missing pkg-config Arrow/Parquet development packages. Install pkg-config, libarrow-dev, and libparquet-dev; see README."
        )

    # example call:
    # python main.py manual --conv_name test43 --query_list 1

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    manual = subparsers.add_parser(
        "manual",
        help="Run a conversation using explicit mode/query args.",
    )
    add_common_args(
        manual,
        include_model=True,
        include_replay=True,
        include_disable_tracing=True,
        include_disable_wandb=True,
        include_conv_name=True,
        include_query_list=True,
        include_continue_run=True,
        include_artifacts_dir=True,
        include_no_preload=True,
        include_notify=True,
        include_replay_cache=True,
        include_auto_u=True,
        include_keep_csv=True,
        include_disable_valtool=True,
        include_disable_artifacts_context=True,
        include_benchmark=True,
        include_auto_finish=True,
        include_conv_mode=True,
        include_is_bespoke_storage=True,
        include_run_tool_offer_trace_option=True,
        include_only_from_llm_cache=True,
        include_only_from_cache=True,
        include_base_parquet_dir=True,
    )
    args = parser.parse_args()
    args.write_query_and_args_files = True

    if args.command == "manual":
        run_conv_wrapper(args)
    else:
        raise Exception(f"Unknown {args.command}")
