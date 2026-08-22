import os
import sys

from src.core.database import DatabaseManager

# Add local src to sys path if not there
sys.path.insert(0, os.getcwd())


print("Initializing DatabaseManager...")
try:
    db = DatabaseManager("data/jobs.db")
    jobs = db.get_all_jobs()
    print(f"Jobs in DB: {len(jobs)}")
    if jobs:
        print(f"First job ID: {jobs[0]['id']}")
    else:
        print("DB is empty via DatabaseManager")
except Exception as e:
    print(f"Error: {e}")
