"""
NL Rule Flow Generator Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.nl_compiler import CompiledCheckConfig


class GeneratedNode(BaseModel):
    node_id: str = Field(..., description="Generated node ID")
    node_type: str = Field(..., description="Node type (source or check)")
    label: str = Field(..., description="Node display label")


class GeneratedConnection(BaseModel):
    connection_id: str = Field(..., description="Generated connection ID")
    source_node: str = Field(..., description="Source node ID")
    target_node: str = Field(..., description="Target node ID")


class GenerateFlowRequest(BaseModel):
    compiled_configs: list[CompiledCheckConfig] = Field(
        ..., min_length=1, description="Compiled check configs to generate flow from"
    )
    target_flow_id: str | None = Field(
        None, description="Existing flow ID to add nodes to. If None, create new flow."
    )
    flow_name: str | None = Field(
        None, max_length=255, description="Name for new flow. Ignored if target_flow_id set."
    )
    flow_description: str | None = Field(None, description="Description for new flow.")
    nl_rule_text: str | None = Field(None, description="Original NL rule text for metadata.")
    parse_request_id: str | None = Field(None, description="Parse request ID for traceability.")


class GenerateFlowResponse(BaseModel):
    flow_id: str = Field(..., description="Flow UUID")
    flow_name: str = Field(..., description="Flow name")
    status: str = Field(default="draft", description="Flow status")
    nodes: list[GeneratedNode] = Field(default_factory=list)
    connections: list[GeneratedConnection] = Field(default_factory=list)
    is_new_flow: bool = Field(..., description="Whether a new flow was created")
