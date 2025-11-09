from github_scanner.config import load_config
from github_scanner.scraper import collect_profile
from github_scanner.llm import enrich_repo_summaries, generate_summary
from github_scanner.report import write_report
import github_scanner.report
import traceback
from pathlib import Path


def main() -> None:
    config = load_config()
    try:
        context = collect_profile("https://github.com/MarcoBetti1", config)
    except Exception:
        traceback.print_exc()
        return
    Path("debug.log").write_text(
        f"report module: {github_scanner.report.__file__}\nrepos: {len(context.repos)}\n",
        encoding="utf-8",
    )
    enrich_repo_summaries(context, config)
    summary = generate_summary(context, config)
    path = write_report(context, summary, config)
    print("wrote", path)


if __name__ == "__main__":
    main()
