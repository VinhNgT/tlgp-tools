import importlib.resources
import json

from tlgp_contracts import ScreenSpec


def test_spec_schema_matches_pydantic_model():
    """Ensure the checked-in spec_schema.json is always in sync with the ScreenSpec model."""
    # Load the checked-in spec_schema.json
    ref = importlib.resources.files("tlgp_contracts") / "spec_schema.json"
    checked_in_schema = json.loads(ref.read_text(encoding="utf-8"))

    # Generate the current schema from the Pydantic model
    current_schema = ScreenSpec.model_json_schema()

    # Compare them
    assert current_schema == checked_in_schema, (
        "spec_schema.json does not match the Pydantic ScreenSpec model definition. "
        "Run the following command to update it:\n"
        "python -c \"import json, tlgp_contracts; "
        "print(json.dumps(tlgp_contracts.ScreenSpec.model_json_schema(), indent=2, ensure_ascii=False))\" "
        "> libs/contracts/src/tlgp_contracts/spec_schema.json"
    )
