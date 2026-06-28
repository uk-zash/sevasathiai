import json
from pathlib import Path

from pydantic import BaseModel, ValidationError 

from app.models import Scheme


DEFAULT_SCHEME_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "schemes.json"


def load_schemes(path : Path = DEFAULT_SCHEME_DB_PATH) -> list[Scheme]:
    
    if not path.exists():
        raise FileNotFoundError(f"Scheme database file not found at {path}")    
    
    raw_text = path.read_text(encoding="utf-8")

    raw_data = json.loads(raw_text)

    if not isinstance(raw_data , list):
        raise ValueError(f"Expected a list of schemes in the JSON file, but got {type(raw_data).__name__}")
    
    try:
        return [Scheme.model_validate(item) for item in raw_data]
    
    except ValidationError as e:
        raise ValueError(f"Error validating scheme data: {e}") from e