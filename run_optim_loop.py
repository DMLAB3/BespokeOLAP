import argparse

from runtime.orchestrator.runner import run_conv_wrapper
from runtime.services import prepare_optimization_run
from utils.cli_config import add_common_args

### RUN CMD
# python run_optim_loop.py --conv brunoptim1-22v1 --bespoke_storage --benchmark tpch --notify --replay_cache --auto_u --auto_finish


def main(args):
    prepared = prepare_optimization_run(args)
    config = prepared.config

    # run conversation
    run_conv_wrapper(config)


def build_parser(*, add_help: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=add_help)
    parser.add_argument(
        "--conv",
        type=str,
        required=True,
        help="Short name for the conversation",
    )
    parser.add_argument(
        "--bespoke_storage",
        action="store_true",
        default=False,
        help="Tag the optimization run as using bespoke storage in the current ./output workspace.",
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
        include_only_from_llm_cache=True,
        include_only_from_cache=True,
    )
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    main(args)
