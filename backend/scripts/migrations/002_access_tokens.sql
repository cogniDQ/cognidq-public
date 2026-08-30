-- Personal Access Tokens Migration
-- Creates table for API tokens that users can generate for programmatic access

CREATE TABLE IF NOT EXISTS access_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    prefix VARCHAR(20) NOT NULL,
    scopes TEXT[] DEFAULT '{}',
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP,
    
    CONSTRAINT valid_name_length CHECK (char_length(name) >= 1)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_access_tokens_user_id ON access_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_access_tokens_token_hash ON access_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_access_tokens_prefix ON access_tokens(prefix);
CREATE INDEX IF NOT EXISTS idx_access_tokens_revoked ON access_tokens(revoked_at) WHERE revoked_at IS NULL;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_access_tokens_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
