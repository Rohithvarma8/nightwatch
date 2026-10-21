"""Simulator settings, read once from the environment (make sim sets MCP_URL from Terraform)."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mcp_url: str
    region: str
    primary_model: str
    fallback_model: str
    voice_id: str
    max_tokens: int

    @classmethod
    def from_env(cls) -> "Settings":
        url = os.environ.get("MCP_URL", "")
        if not url:
            raise SystemExit("MCP_URL is not set (make sim reads it from terraform output mcp_url)")
        return cls(
            mcp_url=url,
            region=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2")),
            primary_model=os.environ.get(
                "SIM_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
            ),
            fallback_model=os.environ.get("SIM_FALLBACK_MODEL", "amazon.nova-lite-v1:0"),
            voice_id=os.environ.get("SIM_VOICE", "Joanna"),
            max_tokens=int(os.environ.get("SIM_MAX_TOKENS", "400")),
        )
