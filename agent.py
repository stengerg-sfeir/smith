#!/usr/bin/env python3
"""Neurosymbolic Python Coding Agent (refactored shim).

The pipeline implementation now lives in the ``agentlib`` package. This
module re-exports every name (functions, classes, constants) from those
modules so that ``import agent`` remains fully backward-compatible, and
exposes the CLI entry point ``main``.

Mechanical refactor only — no behavior change.
"""

import agentlib.config as _config
import agentlib.llm.client as _llm_client
import agentlib.llm.fill as _llm_fill
import agentlib.prompts as _prompts
import agentlib.checks.ast_utils as _ast_utils
import agentlib.naming as _naming
import agentlib.design as _design
import agentlib.generation.model_render as _model_render
import agentlib.generation.helpers as _gen_helpers
import agentlib.generation.repo_contract as _repo_contract
import agentlib.generation.repo_render as _repo_render
import agentlib.generation.service_render as _service_render
import agentlib.generation.cli_render as _cli_render
import agentlib.generation.splice as _splice
import agentlib.kernel.repo.bodies as _repo_bodies
import agentlib.kernel.repo.finder as _repo_finder
import agentlib.kernel.repo.variant as _repo_variant
import agentlib.kernel.service as _kernel_service
import agentlib.kernel.service.common as _service_common
import agentlib.kernel.service.total_in_period as _total_in_period
import agentlib.kernel.service.total_filtered as _total_filtered
import agentlib.kernel.service.export_csv as _export_csv
import agentlib.kernel.service.duplicate_groups as _duplicate_groups
import agentlib.kernel.service.sum_by_group as _sum_by_group
import agentlib.kernel.service.below_foreign_threshold as _below_foreign_threshold
import agentlib.pipeline.generate as _pipeline_generate
import agentlib.pipeline.design as _pipeline_design
import agentlib.pipeline.cli_propagate as _pipeline_cli_propagate
import agentlib.pipeline.manifest as _pipeline_manifest
import agentlib.pipeline.run as _pipeline_run

from agentlib.pipeline.run import main

for _m in (
    _config, _llm_client, _llm_fill, _prompts, _ast_utils, _naming, _design,
    _model_render, _gen_helpers, _repo_contract, _repo_render, _service_render,
    _cli_render, _splice, _repo_bodies, _repo_finder, _repo_variant,
    _kernel_service, _service_common, _total_in_period, _total_filtered,
    _export_csv, _duplicate_groups, _sum_by_group, _below_foreign_threshold,
    _pipeline_generate, _pipeline_design, _pipeline_cli_propagate,
    _pipeline_manifest, _pipeline_run,
):
    for _k, _v in vars(_m).items():
        if not _k.startswith("__"):
            globals()[_k] = _v

# Remove the temporary module aliases and loop variables from the public
# namespace so `import agent` exposes only the re-exported pipeline names.
for _name in (
    "_config", "_llm_client", "_llm_fill", "_prompts", "_ast_utils",
    "_naming", "_design", "_model_render", "_gen_helpers", "_repo_contract",
    "_repo_render", "_service_render", "_cli_render", "_splice",
    "_repo_bodies", "_repo_finder", "_repo_variant", "_kernel_service",
    "_service_common", "_total_in_period", "_total_filtered", "_export_csv",
    "_duplicate_groups", "_sum_by_group", "_below_foreign_threshold",
    "_pipeline_generate", "_pipeline_design", "_pipeline_cli_propagate",
    "_pipeline_manifest", "_pipeline_run", "_k", "_v",
):
    globals().pop(_name, None)


if __name__ == "__main__":
    main()
