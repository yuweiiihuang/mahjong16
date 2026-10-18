# Issue tracker: GitHub

Issues and specs live in yuweiiihuang/mahjong16 on GitHub.
Use the gh CLI from this repository.

## Operations
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state open --json number,title,body,labels`
- Create: `gh issue create --title "..." --body-file <file>`
- Comment: `gh issue comment <number> --body-file <file>`
- Label: `gh issue edit <number> --add-label "..." --remove-label "..."`
- Close: `gh issue close <number>`

Write multiline bodies to a temporary file and pass --body-file.
Publishing to the issue tracker means creating a GitHub issue.
Fetching a ticket means reading the issue and its comments.

## Pull requests as a triage surface
PRs as a request surface: no.

GitHub issues and PRs share a number space. Resolve ambiguous references
with `gh pr view <number>`, falling back to `gh issue view <number>`.
