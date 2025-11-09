# GitHub Scanner

A command line assistant that inspects a GitHub profile, gathers repository metrics and documentation, and produces a polished markdown report using an LLM (OpenAI by default).

## Features
- Scrapes public repository metadata and documentation files via the GitHub API
- Aggregates contribution history from the profile contribution calendar
- Supports configurable modes: documentation-only scanning and owned-repositories filtering
- Generates a concise summary with OpenAI (fallback text provided if the API is unavailable)

## Quick Start
1. **Install dependencies**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install .[llm]
   ```
2. **Configure credentials** (optional for fallback text)
   ```powershell
   $env:OPENAI_API_KEY = "sk-..."
   # Optional: authenticate GitHub requests to increase rate limits
   $env:GITHUB_TOKEN = "ghp_..."
   ```
3. **Run the scanner**
   ```powershell
   github-scanner https://github.com/octocat
   ```

## Configuration
Adjust `config/settings.yaml` to tweak behavior:

- `modes.docs_only`: when `true`, only documentation files are downloaded.
- `modes.owned_repos_only`: when `true`, limit analysis to repositories owned by the profile.
- `llm.*`: provider metadata (currently optimized for OpenAI).
- `output.directory`: destination folder for generated reports.
- `output.show_repo_tables`: when `true`, include a detail table per repository; set to `false` for narrative-only entries.

Override any setting from the CLI:
```powershell
github-scanner https://github.com/octocat --no-docs-only --output-dir reports/custom
```

## Development
- Formatting: standard library conventions (no external formatter enforced).
- Tests (if added) can be executed with `pytest`.

## Roadmap Ideas
- Extend scanning to repositories the user contributes to but does not own.
- Add richer code insight when documentation-only mode is disabled.
- Support additional LLM providers via a pluggable adapter interface.
