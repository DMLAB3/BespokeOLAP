import argparse
from pathlib import Path

import run_gen_base_impl
import run_gen_storage_plan
from utils.cli_config import add_common_args


def _default_storage_conv(base_conv: str) -> str:
    prefix = "basef"
    if not base_conv.startswith(prefix):
        raise ValueError(
            f"--conv must start with {prefix!r} when --storage-conv is omitted."
        )
    return "storageplan" + base_conv[len(prefix) :]


def main(args: argparse.Namespace) -> None:
    storage_conv = args.storage_conv or _default_storage_conv(args.conv)
    storage_plan_path = Path("output") / "storage_plan.txt"

    storage_args = argparse.Namespace(**vars(args))
    storage_args.conv = storage_conv
    run_gen_storage_plan.main(storage_args)

    if not storage_plan_path.exists():
        raise FileNotFoundError(
            f"Expected storage plan at {storage_plan_path} after storage-plan run."
        )

    base_args = argparse.Namespace(**vars(args))
    base_args.with_storage_plan = True
    base_args.storage_plan_path = storage_plan_path.as_posix()
    run_gen_base_impl.main(base_args)


def build_parser(*, add_help: bool = True) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=add_help)
    parser.add_argument(
        "--conv",
        type=str,
        required=True,
        help=(
            "Base implementation conversation name, e.g. basef1-2v1. The "
            "storage-plan name defaults to storageplan1-2v1."
        ),
    )
    parser.add_argument(
        "--storage-conv",
        type=str,
        default=None,
        help="Optional explicit storage-plan conversation name.",
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
    main(build_parser().parse_args())
