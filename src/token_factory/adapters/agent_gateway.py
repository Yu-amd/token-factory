"""Agent Gateway adapters — mock default for Friday; agentgateway later."""

from __future__ import annotations

from token_factory.adapters.types import AdapterMode, GovernanceDecision, RequestContext


class MockAgentGatewayAdapter:
    """Deterministic governance for SVP demo. Clearly labeled mock/demo."""

    implementation = "mock"
    mode: AdapterMode = "mock"

    # Principals allowed for Engineering demo pack
    ALLOWED_PRINCIPALS = frozenset(
        {"engineering.user", "eng.user", "svp.demo", "demo.engineer"}
    )
    DENY_TOOLS = frozenset({"exfiltrate_secrets", "delete_cluster", "raw_shell"})

    def authorize(self, ctx: RequestContext) -> GovernanceDecision:
        authn = "PASS" if ctx.principal else "FAIL"
        authz = "PASS" if ctx.principal in self.ALLOWED_PRINCIPALS else "DENY"
        quota = "PASS"
        mcp_policy = "N/A"
        a2a_policy = "N/A"
        allowed = authn == "PASS" and authz == "PASS" and quota == "PASS"
        reason = ""

        if ctx.request_type == "mcp":
            tool = (ctx.tool_name or "").strip() or "unknown_tool"
            if tool in self.DENY_TOOLS or ctx.data_classification == "confidential" and tool.startswith("external_"):
                mcp_policy = "DENY"
                allowed = False
                reason = f"MCP policy denied tool '{tool}'"
            else:
                mcp_policy = "PASS"
        elif ctx.request_type == "a2a":
            if not ctx.agent_task:
                a2a_policy = "DENY"
                allowed = False
                reason = "A2A policy requires agent_task"
            else:
                a2a_policy = "PASS"
        elif ctx.request_type == "model":
            mcp_policy = "N/A"
            a2a_policy = "N/A"

        if authz == "DENY":
            allowed = False
            reason = reason or f"AuthZ denied principal '{ctx.principal}'"

        return GovernanceDecision(
            allowed=allowed,
            authn=authn,
            authz=authz,
            mcp_policy=mcp_policy,
            a2a_policy=a2a_policy,
            quota=quota,
            reason=reason,
            implementation=self.implementation,
            mode=self.mode,
        )


class DisabledAgentGatewayAdapter:
    """Pass-through — Phase 2 governance disabled; Phase 1 model path unaffected."""

    implementation = "disabled"
    mode: AdapterMode = "disabled"

    def authorize(self, ctx: RequestContext) -> GovernanceDecision:
        del ctx
        return GovernanceDecision(
            allowed=True,
            authn="SKIP",
            authz="SKIP",
            mcp_policy="SKIP",
            a2a_policy="SKIP",
            quota="SKIP",
            reason="Agent Gateway disabled — Phase 1 path only",
            implementation=self.implementation,
            mode=self.mode,
        )
