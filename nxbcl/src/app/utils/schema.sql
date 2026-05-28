-- SQLite database schema for NXBCL Launcher

CREATE TABLE IF NOT EXISTS pow_challenges (
    token TEXT PRIMARY KEY,
    salt TEXT NOT NULL,
    zero_prefix TEXT NOT NULL,
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    solved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS instances (
    instance_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    wallet_address TEXT NOT NULL,
    private_key TEXT NOT NULL,
    deploy_address TEXT,
    rpc_port INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS solves (
    user_id TEXT NOT NULL,
    challenge_id TEXT NOT NULL,
    solved BOOLEAN NOT NULL DEFAULT 0,
    solved_at TIMESTAMP,
    PRIMARY KEY(user_id, challenge_id)
);

CREATE TABLE IF NOT EXISTS repos (
    repo_url TEXT PRIMARY KEY,
    branch TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    synced_at TIMESTAMP NOT NULL
);
