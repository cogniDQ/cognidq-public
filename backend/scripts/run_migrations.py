#!/usr/bin/env python3
"""
Database migration runner
"""

import sys
from pathlib import Path

import psycopg2

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import settings


def run_migrations():
    """Run all SQL migration files in order"""
    migrations_dir = Path(__file__).parent / "migrations"

    # Connect to database
    try:
        conn = psycopg2.connect(settings.DATABASE_URL)
        conn.autocommit = True
        cursor = conn.cursor()

        print(f"Connected to database: {settings.DATABASE_URL}")

        # Get all SQL files sorted by name
        migration_files = sorted(migrations_dir.glob("*.sql"))

        if not migration_files:
            print("No migration files found")
            return

        print(f"\nFound {len(migration_files)} migration file(s)")

        # Run each migration
        for migration_file in migration_files:
            print(f"\nRunning migration: {migration_file.name}")

            with open(migration_file) as f:
                sql_content = f.read()

            try:
                cursor.execute(sql_content)
                print(f"✓ Successfully executed {migration_file.name}")
            except Exception as e:
                print(f"✗ Error executing {migration_file.name}: {e}")
                raise

        # Verify tables were created
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()

        print("\n✓ Migration complete!")
        print("\nCreated tables:")
        for table in tables:
            print(f"  - {table[0]}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
