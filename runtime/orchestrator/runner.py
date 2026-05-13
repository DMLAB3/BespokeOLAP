from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from agents.extensions.memory import AdvancedSQLiteSession
from agents.tracing import set_tracing_disabled
from dotenv import load_dotenv

import wandb
from conversations.conversation import (
    COMPACTION_MARKER,
    VALIDATE_OFF,
    VALIDATE_ON,
    VALIDATE_OUTPUT_STDOUT_OFF,
    VALIDATE_OUTPUT_STDOUT_ON,
)
from conversations.optimization_conversation import OptimizationConversation
from conversations.scripted_conversation import ScriptedConversation
from dataset.dataset_tables_dict import get_dataset_name
from dataset.query_gen_factory import get_placeholders_fn, get_query_gen
from runtime.agent.callbacks import DspyWandbCallback
from runtime.agent.dspy_agent import DspyBespokeAgent
from runtime.agent.toolbox import DspyToolbox
from llm_cache.logger import setup_logging
from llm_cache.utils import ask_yes_no
from runtime.agent.session_store import DspySessionStore
from runtime.config import RuntimeConfig
from tools.fasttest import copy_template_to
from tools.fasttest.compile import CompileTool
from tools.fasttest.run import RunTool
from tools.validate_tool.query_validator_class import QueryValidator
from tools.validate_tool.sf_list_gen import gen_sf
from utils.general_utils import write_query_and_args_file
from utils.model_setup import setup_dspy_instructor_model_config, setup_dspy_model_config
from utils.truncate_model_log import truncate_model_final_output
from utils.wandb_stats_logging import WandbRunHook
from utils.weave_cache import configure_weave_cache_dirs

logger = logging.getLogger(__name__)


def _unique_scale_factors(scale_factors: list[float]) -> list[float]:
    unique: list[float] = []
    for scale_factor in scale_factors:
        if scale_factor not in unique:
            unique.append(scale_factor)
    return unique


def _clean_workspace_without_git(workspace_path: Path) -> None:
    for child in workspace_path.iterdir():
        if child.name == "logs":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


async def run_runtime(args: argparse.Namespace) -> None:
    workspace_path = Path("./output")
    workspace_path.mkdir(exist_ok=True)

    cache_path = Path(args.artifacts_dir) / "cache"
    conversations_dir = Path(args.artifacts_dir) / "conversations"

    dataset_version = None
    if args.benchmark == "ceb":
        dataset_version = "3"

    gen_query_fn = get_query_gen(args.benchmark)
    gen_placeholders_fn = get_placeholders_fn(
        args.benchmark, cache_path / "placeholders_cache"
    )

    query_list = [q.strip() for q in args.query_list.split(",")]

    if (
        getattr(args, "start_snapshot", None) is not None
        or getattr(args, "storage_plan_snapshot", None) is not None
    ):
        raise ValueError(
            "Git snapshots are disabled in the DSPy runtime. "
            "--start_snapshot and --storage_plan_snapshot are not supported."
        )

    storage_plan = None
    storage_plan_path = getattr(args, "storage_plan_path", None)
    if storage_plan_path:
        storage_plan = Path(storage_plan_path).read_text()

    artifacts_in_context = ""
    disable_artifacts_context = getattr(args, "disable_artifacts_context", False)
    if not args.continue_run:
        logger.warning(
            f'Cleaning "{workspace_path}" before starting a fresh no-snapshot run.'
        )
        _clean_workspace_without_git(workspace_path)

        template_artifacts = copy_template_to(workspace_path, args.benchmark)
        if not disable_artifacts_context:
            artifacts_in_context += template_artifacts

        logger.info(
            "Generating query and args files for queries: %s/%s",
            args.benchmark,
            query_list,
        )
        query_artifacts = write_query_and_args_file(
            benchmark_name=args.benchmark,
            gen_placeholders_fn=gen_placeholders_fn,
            query_list=query_list,
            out_dir=workspace_path.as_posix(),
            use_fasttest_format=True,
            storage_plan=storage_plan,
        )
        if not disable_artifacts_context:
            artifacts_in_context += query_artifacts
    else:
        logger.warning(f'Continuing current files in "{workspace_path}".')

    timestamp = getattr(args, "_log_timestamp", datetime.now().strftime("%Y%m%d_%H%M%S"))
    log_path = workspace_path / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    run_log_path = log_path / f"{timestamp}_{args.conv_name}.log"
    llm_log_path = log_path / f"{timestamp}_{args.conv_name}_llm_calls.jsonl"
    setup_logging(logging.DEBUG, run_log_path)
    logger.info("Logging to %s", run_log_path)
    logger.info("Logging full LLM calls to %s", llm_log_path)

    parquet_path = args.artifacts_dir + f"/{get_dataset_name(args.benchmark)}_parquet/"

    max_scale_factor = getattr(args, "max_scale_factor", None)
    if max_scale_factor is None:
        max_scale_factor = 1

    wandb_metrics_hook: WandbRunHook | None = None
    if not args.disable_wandb:
        wandb_metrics_hook = WandbRunHook(
            model=args.model,
            git_snapshotter=None,
            working_dir=workspace_path,
            cloc_cache_dir=cache_path / "cloc_cache",
        )

    verify_sf_list, _ = gen_sf(args.benchmark)

    compile_cache_dir = cache_path / "compile"
    query_validator: QueryValidator | None = None
    if not args.disable_valtool:
        query_validator = QueryValidator(
            benchmark=args.benchmark,
            gen_query_fn=gen_query_fn,
            sf_list=_unique_scale_factors(verify_sf_list + [max_scale_factor]),
            parquet_path=parquet_path,
            wandb_pin_worker=True,
            all_query_ids=query_list,
            num_random_query_instantiations=10,
            query_cache_dir=cache_path / "query_cache",
            validate_cache_dir=cache_path / "validate_tool",
            workspace_path=workspace_path,
            git_snapshotter=None,
        )

    compile_tool: CompileTool | None = None
    run_tool: RunTool | None = None
    if query_validator is not None:
        dataset_name = get_dataset_name(args.benchmark)
        compile_tool = CompileTool(
            cwd=workspace_path,
            compile_cache_dir=compile_cache_dir,
            git_snapshotter=None,
            wandb_metrics_hook=wandb_metrics_hook,
        )
        run_tool = RunTool(
            cwd=workspace_path,
            query_validator=query_validator,
            wandb_metrics_hook=wandb_metrics_hook,
            compile_cache_dir=compile_cache_dir,
            git_snapshotter=None,
            dataset_name=dataset_name,
            base_parquet_dir=f"{args.base_parquet_dir}/{dataset_name}_parquet/",
            only_from_cache=args.only_from_cache,
        )

    dspy_callbacks = (
        [DspyWandbCallback(wandb_metrics_hook, llm_log_path=llm_log_path)]
        if wandb_metrics_hook
        else [DspyWandbCallback(None, llm_log_path=llm_log_path)]
    )
    model_name, lm = setup_dspy_model_config(args.model, callbacks=dspy_callbacks)
    instructor_model_name = None
    instructor_lm = None
    if getattr(args, "use_rlm_instructor", False):
        instructor_model_name, instructor_lm = setup_dspy_instructor_model_config(
            args.rlm_instructor_model
        )
    underlying_session = AdvancedSQLiteSession(
        session_id=args.conv_name, create_tables=True
    )
    session_store = DspySessionStore(
        cache_path / "dspy_sessions" / f"{args.conv_name}.json"
    )

    config_kwargs: Dict[str, Any] = {"max_workspace_csv_size_mb": 5.0}
    if dataset_version is not None:
        config_kwargs["dataset_version"] = dataset_version

    dspy_tools = DspyToolbox(
        workspace_path=workspace_path,
        cache_path=cache_path,
        snapshotter=None,
        compile_tool=compile_tool,
        run_tool=run_tool,
        wandb_metrics_hook=wandb_metrics_hook,
    )
    model = DspyBespokeAgent(
        model_name=model_name,
        lm=lm,
        tools=dspy_tools,
        llm_cache_dir=cache_path / "dspy_llm_cache",
        snapshotter=None,
        workspace_path=workspace_path,
        stop_on_cache_miss=args.replay
        or args.only_from_llm_cache
        or args.only_from_cache,
        query_gen_list=query_list,
        artifacts_in_context=artifacts_in_context,
        config_kwargs=config_kwargs,
        callbacks=dspy_callbacks,
        instructor_model_name=instructor_model_name,
        instructor_lm=instructor_lm,
    )

    workspace_contract = "".join(
        [
            f"You can edit files inside {workspace_path} using the apply_patch tool. ",
            "When modifying an existing file, provide a unified diff and set op_type ",
            "to create_file, update_file, or delete_file. ",
            "You can run shell commands using the shell tool. ",
            "Do not emit argv form for shell commands. ",
            "Finish only after required files are written and checks requested by the task are complete. ",
        ]
    )
    if query_validator is not None:
        workspace_contract += (
            "You can compile the code using the compile tool. "
            "You can run a list of queries using the run tool. The run tool "
            "automatically compiles the code. Specify query_id when running a "
            "subset; omit query_id to run all queries."
        )

    logger.info("Workspace root: %s", workspace_path)
    logger.info("Using model: %s", model)

    async def handle_prompt(
        text: str,
        short_desc: Optional[str],
        idx: int,
        max_turns: Optional[int] = None,
    ) -> Optional[str]:
        if max_turns is None:
            max_turns = 75

        if text == COMPACTION_MARKER:
            logger.info("Triggering compaction at prompt index %s", idx)
            branch_id = getattr(underlying_session, "_current_branch_id", "main")
            session_items = await underlying_session.get_items()
            recent_context = session_store.render_context(
                branch_id=branch_id,
                session_items=session_items,
                artifacts_in_context=(
                    artifacts_in_context if not disable_artifacts_context else None
                ),
            )
            summary = await asyncio.to_thread(
                model.compact_context,
                session_store.get_summary(branch_id),
                recent_context,
            )
            session_store.compact(summary, branch_id=branch_id)
            return None

        if text == VALIDATE_ON:
            assert run_tool is not None
            run_tool.parse_out_and_validate_output = True
            logger.info("Enabled output parsing and validation at prompt index %s", idx)
            return None
        if text == VALIDATE_OFF:
            assert run_tool is not None
            run_tool.parse_out_and_validate_output = False
            logger.info(
                "Disabled output parsing and validation at prompt index %s", idx
            )
            return None
        if text == VALIDATE_OUTPUT_STDOUT_ON:
            assert query_validator is not None
            query_validator.output_stdout_stderr = True
            logger.info(
                "Enabled output stdout in validation results at prompt index %s", idx
            )
            return None
        if text == VALIDATE_OUTPUT_STDOUT_OFF:
            assert query_validator is not None
            query_validator.output_stdout_stderr = False
            logger.info(
                "Disabled output stdout in validation results at prompt index %s", idx
            )
            return None

        logger.info("=" * 80)
        logger.info(text)
        logger.info("=" * 80)

        if wandb_metrics_hook is not None:
            wandb_metrics_hook.prompt_idx = idx
            wandb_metrics_hook.current_prompt = text
            wandb_metrics_hook.current_prompt_descriptor = short_desc

        branch_id = getattr(underlying_session, "_current_branch_id", "main")
        session_items = await underlying_session.get_items()
        conversation_context = session_store.render_context(
            branch_id=branch_id,
            session_items=session_items,
            artifacts_in_context=(
                artifacts_in_context if not disable_artifacts_context else None
            ),
        )

        final_output = await asyncio.to_thread(
            model.run,
            task=text,
            conversation_context=conversation_context,
            workspace_contract=workspace_contract,
            max_turns=max_turns,
            wandb_metrics_hook=wandb_metrics_hook,
            prompt_idx=idx,
            short_desc=short_desc,
        )

        await underlying_session.add_items(
            [
                {"role": "user", "content": text},
                {"role": "assistant", "content": final_output},
            ]
        )
        session_store.append_turn(text, final_output, branch_id=branch_id)

        logger.info(truncate_model_final_output(final_output))

        return final_output

    conv_args = dict(
        conversation_json_path=conversations_dir / f"{args.conv_name}.json",
        callback=handle_prompt,
        auto_finish=args.auto_finish,
        replay_cache=args.replay_cache,
        auto_u=args.auto_u,
        replay=args.replay,
        notify=args.notify,
        model=model,
    )
    if args.conv_mode == "scripted":
        conv = ScriptedConversation(**conv_args)
    elif args.conv_mode == "optimization":
        assert query_validator is not None, (
            "query_validator must be provided for optimization conversation"
        )
        assert run_tool is not None
        conv = OptimizationConversation(
            query_ids=query_list,
            bespoke_storage=args.is_bespoke_storage,
            run_tool=run_tool,
            verify_sf_list=verify_sf_list,
            benchmark_sf=max_scale_factor,
            query_validator=query_validator,
            git_snapshotter=None,
            revert_on_regression=False,
            session=underlying_session,
            wandb_run_hook=wandb_metrics_hook,
            **conv_args,
        )
    else:
        raise ValueError(f"Unknown conversation mode: {args.conv_mode}")

    await conv.run()

    logger.debug("Model cache total saved: $%0.6f", model.total_saved)

    if not args.disable_wandb:
        assert wandb_metrics_hook is not None
        wandb.log(
            {
                "final/total_cost_usd": wandb_metrics_hook.total_stats["cost_usd"],
                "final/total_turns": wandb_metrics_hook.last_turn,
                "final/total_tokens": wandb_metrics_hook.total_stats["output_tokens"]
                + wandb_metrics_hook.total_stats["input_tokens"]
                + wandb_metrics_hook.total_stats["reasoning_tokens"],
                "final/num_prompts": wandb_metrics_hook.prompt_idx + 1,
            }
        )


class RuntimeRunner:
    """Entry point for runtime orchestration during rewrite migration."""

    @staticmethod
    def from_args(args: argparse.Namespace) -> RuntimeConfig:
        return RuntimeConfig(
            benchmark=args.benchmark,
            conv_name=args.conv_name,
            query_list=args.query_list,
            artifacts_dir=args.artifacts_dir,
            base_parquet_dir=args.base_parquet_dir,
            conv_mode=args.conv_mode,
            continue_run=args.continue_run,
            replay=args.replay,
            disable_tracing=args.disable_tracing,
            disable_wandb=args.disable_wandb,
            model=args.model,
        )

    def run(self, _config: RuntimeConfig, args: argparse.Namespace) -> None:
        run_conv_wrapper(args)


def run_conv_wrapper(args: argparse.Namespace) -> None:
    if args.continue_run:
        ask_yes_no(
            "Are you really sure you want to continue the current output workspace? This does not start from a fresh template and might include unwanted files already present in output/."
        )

    args._log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    setup_logging(logging.DEBUG)

    load_dotenv()
    # Keep low-level agents.custom_span usage quiet in DSPy runtime mode.
    set_tracing_disabled(True)
    if not args.disable_tracing and not args.disable_wandb:
        configure_weave_cache_dirs()
        import weave

        entity = os.getenv("WANDB_ENTITY", "learneddb")
        project = os.getenv("WANDB_PROJECT", "bespoke-olap-agents")

        weave.init(
            f"{entity}/{project}",
            settings={"log_level": "INFO", "print_call_link": False},
        )

        tags = [args.benchmark]
        if args.is_bespoke_storage:
            tags.append("bespoke-storage")

        wandb.init(
            config=vars(args),
            entity=entity,
            project=project,
            name=f"{args.conv_name}",
            tags=tags,
        )

    asyncio.run(run_runtime(args))
