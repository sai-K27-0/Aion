-- Aion Database Initialization Script
-- ====================================
-- This script runs when PostgreSQL container first starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "ltree";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE aion TO aion;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Aion database initialized successfully';
END $$;
