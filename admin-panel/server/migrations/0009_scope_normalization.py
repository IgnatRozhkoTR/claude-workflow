"""
Normalize legacy scope values in discussions.
"""
from yoyo import step

step("""
    UPDATE discussions SET scope = 'review' WHERE scope IN ('diff', 'file')
""")
