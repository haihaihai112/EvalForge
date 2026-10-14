# Reference and implementation notes

EvalForge implements its own evaluation, persistence, tracing, API and frontend.
It does not vendor or import DeepEval, Ragas, Phoenix, OpenTelemetry or OpenInference.

The architecture investigation used:

- confident-ai/deepeval, commit `016946f6d770f8bc4e2f63f665140aea527d6641`, Apache-2.0: claim extraction, verdict scoring and synthetic input evolution patterns.
- Arize-ai/phoenix, commit `9793e30feae1949f7bf972613aaf4275dc0b1b0b`, root ELv2; selected subpackage metadata differs as recorded in docs/phoenix-source-audit.md: span/context concepts, ingestion and SQLite design observations.
- User-supplied rea-agents 6.4.0 workflow instructions: evidence-led investigation. Its own skill routes complete-source analysis to ordinary repository tools; no decompilation or binary Evidence claims are made here.

No upstream server implementation or prompt template was copied into the application. Prompts and domain fixtures are written for this project. The included logistics SOP is fictional and solely for demonstration. Dependencies retain their own licenses.
