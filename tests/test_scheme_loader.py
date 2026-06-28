import json

import pytest

from app.scheme_loader import load_schemes


def test_load_schemes_loads_verified_database() -> None:
    schemes = load_schemes()

    assert len(schemes) >= 1

    scheme_ids = [scheme.scheme_id for scheme in schemes]

    assert "aicte_pragati_degree" in scheme_ids


def test_load_schemes_rejects_invalid_category(tmp_path) -> None:
    invalid_database_path = tmp_path / "schemes.json"

    invalid_database = [
        {
            "scheme_id": "bad_scheme",
            "name": "Bad Scheme",
            "category": "scholarships",
            "government_level": "central",
            "state": None,
            "summary": "This invalid scheme is used only for testing validation.",
            "target_groups": [],
            "benefits": [],
            "required_documents": [],
            "eligibility_text": [],
            "application_steps": [],
            "application_window": None,
            "official_apply_url": None,
            "sources": [
                {
                    "source_type": "official_portal",
                    "title": "Invalid test source",
                    "publisher": "Test Publisher",
                    "url": "https://example.gov.in/test",
                    "last_checked_at": "2026-06-27",
                    "notes": None,
                }
            ],
        }
    ]

    invalid_database_path.write_text(
        json.dumps(invalid_database),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_schemes(invalid_database_path)