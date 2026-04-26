Run the eval scoreboard generator for Task 2.

Usage: /score [results_file] [--update-readme] [--readme-path PATH]

- results_file: path to eval/results/<ts>.json (default: most-recent file)
- --update-readme: splice the scoreboard into task2/README.md
- --readme-path: override the README path

```bash
cd task2 && uv run python scripts/score.py $ARGUMENTS
```
