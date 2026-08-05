# NEO_CODE.md — Project Instructions for Neo Code

<!-- Hermes Notes -->

## Project Preferences

- **Language**: Chinese preferred for communication, English for code
- **Code style**: Minimal comments, no decorative markers, direct execution
- **Tool preference**: edit_file for modifications, write_file only for new files

## Pitfalls & Gotchas

- File encoding: always use UTF-8
- PowerShell: use `pwsh` or `powershell` commands, not bash syntax on Windows
- Large files: use read_file with offset/limit for files >2000 lines

## Reusable Workflows

- **Code review**: read_file → grep_search for patterns → diff_review → edit_file → lsp_check
- **Documentation**: glob_search for README → read_file → edit_file incrementally
- **Debugging**: read_file at error line → grep_search for related code → run_interpreter/run_command to test
