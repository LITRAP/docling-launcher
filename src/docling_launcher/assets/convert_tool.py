"""Runs INSIDE Docling's environment: Docling's own command line, with two model choices
its command line does not offer.

    python convert_tool.py [--describe-model small|better] [--chart-model v4|2b] convert <docling args...>

Everything after the launcher's own two options is handed to `docling convert` unchanged,
so the flags, the output files and their names are exactly the command line's. Before that
hand-over the defaults Docling would use are swapped:

* --describe-model better   picture descriptions from ibm-granite/granite-vision-3.3-2b
                            (2 billion parameters, built for documents) with an instruction
                            written for technical readers, instead of SmolVLM-256M;
* --chart-model 2b          charts through ibm-granite/granite-vision-3.3-2b-chart2csv
                            (6 GB) instead of granite-vision-4.1-4b (8 GB) — chosen by the
                            launcher when the describing model is on too, so both fit on a
                            16 GB card.

Docling 2.126 sets these only in its Python interface; swapping the pydantic defaults and
rebuilding the option classes is the smallest change that reaches every pipeline the
command line builds (PDF, images, Word, ...). Shipped inside the exe as an asset.
"""
from __future__ import annotations

import sys

DESCRIBE_PROMPT = (
    "Describe this figure for a technical reader in a few precise sentences: what it shows, "
    "the axes or labels, the key values or components, and what it means. If it contains "
    "text, quote the important text. Do not speculate beyond what is visible."
)
BETTER_DESCRIBE_REPO = "ibm-granite/granite-vision-3.3-2b"


def apply_choices(describe_model: str, chart_model: str) -> None:
    from docling.datamodel import pipeline_options as po
    from docling.datamodel.chart_extraction_options import (
        ChartExtractionModelKind,
        ChartExtractionModelOptions,
    )

    if describe_model == "better":
        better = po.PictureDescriptionVlmOptions(repo_id=BETTER_DESCRIBE_REPO, prompt=DESCRIBE_PROMPT)
        better.generation_config["max_new_tokens"] = 320
        # The 2B model can fall into a stutter on busy figures ("Main Apticon, Main Apticon,
        # ..." - seen on a manual's parts diagram); a mild brake on repeats stops it.
        better.generation_config["repetition_penalty"] = 1.15
        for cls in (po.PdfPipelineOptions, po.ConvertPipelineOptions):
            cls.model_fields["picture_description_options"].default = better
            cls.model_rebuild(force=True)

    if chart_model == "2b":
        ChartExtractionModelOptions.model_fields["model"].default = ChartExtractionModelKind.GRANITE_VISION
        ChartExtractionModelOptions.model_rebuild(force=True)
        for cls in (po.PdfPipelineOptions, po.ConvertPipelineOptions):
            if "chart_extraction_options" in cls.model_fields:
                cls.model_fields["chart_extraction_options"].default = ChartExtractionModelOptions()
                cls.model_rebuild(force=True)


def main(argv: list[str]) -> int:
    describe_model, chart_model = "small", "v4"
    rest = list(argv)
    while rest and rest[0].startswith("--"):
        flag = rest.pop(0)
        if flag == "--describe-model" and rest:
            describe_model = rest.pop(0)
        elif flag == "--chart-model" and rest:
            chart_model = rest.pop(0)
        else:
            print(f"convert_tool: unknown option {flag}")
            return 2
    apply_choices(describe_model, chart_model)
    sys.argv = ["docling", *rest]
    from docling.cli.main import app
    app()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
