"""
DRIVE — AI SSD Guardian
Package init.

Imports are intentionally minimal here (models only) to allow
unit tests to import the package without requiring Flask.
For the Flask app, import from app.py instead.
"""
from models import DriveInfo, FrameworkInfo, ShieldStatus, ScanResult

__all__ = ["DriveInfo", "FrameworkInfo", "ShieldStatus", "ScanResult"]
__version__ = "1.0.0"