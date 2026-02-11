CREATE TABLE IF NOT EXISTS moderation_results (
    id SERIAL PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES ads(item_id) ON DELETE CASCADE,
    status VARCHAR(20),
    is_violation BOOLEAN,
    probability FLOAT,
    error_message TEXT, 
    created_at TIMESTAMP,
    processed_at TIMESTAMP
);