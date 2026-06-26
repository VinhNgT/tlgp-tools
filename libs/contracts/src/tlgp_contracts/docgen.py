from pydantic import BaseModel, Field

class DocGenResult(BaseModel):
    """The structured JSON output emitted by the doc-gen CLI and consumed by the MCP Server."""

    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    components: int = 0
    non_leaf: int = 0
    ui_elements: int = 0
    interactions: int = 0
    apis: int = 0
    images: int = 0
    discrepancies: int = 0

    output_path: str | None = None
    tables: int | None = None
