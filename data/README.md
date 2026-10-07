# data

The app's own data for the Contxt in this folder: its database (`workspace.sqlite`),
uploaded files (`objects/`), your sign-in key (`secrets/`) and automatic backups taken before
every database upgrade (`backups/`).

`uv run contxt setup` fills it the first time the app starts. Git ignores everything here but
this file: it holds your sign-in key, so never commit or share it. Back it up with
`uv run contxt backup`.
