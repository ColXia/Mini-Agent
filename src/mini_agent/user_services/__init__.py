"""User services package for v11.3.

This package provides the User Service Layer that sits between
User Surfaces (TUI / Desktop / Remote) and the Business Logic Layer.

Key principles:
- User services provide stable interfaces for surfaces
- User services aggregate multiple business services
- User services organize APIs for user interaction
- User services do NOT directly hold business truth

The User Service Layer includes:
- AgentUserService: Agent state and control
- WorkspaceUserService: Workspace management
- ModelUserService: Model configuration
- CommandUserService: Command execution
"""

from __future__ import annotations

__all__: list[str] = []
