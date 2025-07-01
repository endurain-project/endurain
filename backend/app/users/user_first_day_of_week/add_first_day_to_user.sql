-- Migration to add first_day_of_week column to users table
-- This should be added as a new migration file in your migrations directory

ALTER TABLE users 
ADD COLUMN first_day_of_week INTEGER DEFAULT 0 CHECK (first_day_of_week >= 0 AND first_day_of_week <= 6);

-- Add comment to document the column
COMMENT ON COLUMN users.first_day_of_week IS 'First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday';

-- Update existing users to have the default value (Sunday = 0)
UPDATE users SET first_day_of_week = 0 WHERE first_day_of_week IS NULL;