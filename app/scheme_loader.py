"""Load and validate the local scheme database."""

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError 

from app.models import Scheme


# Default location for the curated verified scheme JSON file.
DEFAULT_SCHEME_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.json"


def load_schemes(path : Path = DEFAULT_SCHEME_DB_PATH) -> list[Scheme]:
    """Read scheme JSON from disk and convert each entry into a Scheme model.

    Args:
        path: JSON file containing a top-level list of scheme definitions.

    Raises:
        FileNotFoundError: If the scheme database path is missing.
        ValueError: If the JSON shape or any scheme entry is invalid.
    """
    
    if not path.exists():
        raise FileNotFoundError(f"Scheme database file not found at {path}")    
    
    raw_text = path.read_text(encoding="utf-8")

    raw_data = json.loads(raw_text)

    if not isinstance(raw_data , list):
        raise ValueError(f"Expected a list of schemes in the JSON file, but got {type(raw_data).__name__}")
    
    try:
        # Pydantic validation catches missing required fields, enum typos, and
        # malformed eligibility rules before the agent tries to use them.
        return [Scheme.model_validate(item) for item in raw_data]
    
    except ValidationError as e:
        raise ValueError(f"Error validating scheme data: {e}") from e
