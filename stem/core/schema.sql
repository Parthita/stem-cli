-- stem metadata schema (append-only)

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS branches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id TEXT NOT NULL,
  slug TEXT NOT NULL,
  user TEXT NOT NULL,
  prompt TEXT NOT NULL,
  summary TEXT NOT NULL,
  git_branch TEXT NOT NULL,
  created_at TEXT NOT NULL,
  repo_root TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS branches_branch_id_idx
  ON branches(repo_root, branch_id);

CREATE INDEX IF NOT EXISTS branches_created_at_idx
  ON branches(repo_root, created_at);

CREATE TABLE IF NOT EXISTS leaves (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id TEXT NOT NULL,
  leaf_id TEXT NOT NULL,
  prompt TEXT NOT NULL,
  summary TEXT NOT NULL,
  git_commit TEXT NOT NULL,
  created_at TEXT NOT NULL,
  repo_root TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS leaves_leaf_id_idx
  ON leaves(repo_root, branch_id, leaf_id);

CREATE INDEX IF NOT EXISTS leaves_branch_id_idx
  ON leaves(repo_root, branch_id, created_at);

CREATE TABLE IF NOT EXISTS jumps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  branch_id TEXT NOT NULL,
  leaf_id TEXT NOT NULL,
  prompt TEXT NOT NULL,
  summary TEXT NOT NULL,
  ancestry TEXT NOT NULL,
  created_at TEXT NOT NULL,
  repo_root TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS jumps_created_at_idx
  ON jumps(repo_root, created_at);

CREATE TABLE IF NOT EXISTS command_exec (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nonce TEXT NOT NULL,
  command TEXT NOT NULL,
  source_file TEXT NOT NULL,
  created_at TEXT NOT NULL,
  repo_root TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS command_exec_nonce_idx
  ON command_exec(repo_root, nonce);
