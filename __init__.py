"""
DRIVE — AI SSD Guardian
Package init.

Imports are intentionally minimal here (models only) to allow
unit tests to import the package without requiring Flask.
For the Flask app, import from app.py instead.
"""
from models import DriveInfo, FrameworkInfo, ScanResult
from shield_manager import ShieldStatus

__all__ = ["DriveInfo", "FrameworkInfo", "ScanResult", "ShieldStatus"]
__version__ = "1.2.0"