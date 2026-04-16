"""Tests for self-improving skill system."""

from __future__ import annotations

import pytest

from mini_agent.agent_core.skills.self_improve import (
    SelfImprovingSkillEngine,
    SkillPerformanceMetrics,
)


def test_skill_performance_metrics_defaults():
    metrics = SkillPerformanceMetrics()
    assert metrics.total_invocations == 0
    assert metrics.successful_invocations == 0
    assert metrics.failed_invocations == 0
    assert metrics.success_rate == 0.0
    assert metrics.avg_latency_ms == 0.0


def test_skill_performance_metrics_success_rate():
    metrics = SkillPerformanceMetrics()
    metrics.total_invocations = 10
    metrics.successful_invocations = 8
    metrics.failed_invocations = 2

    assert metrics.success_rate == 0.8


def test_skill_performance_metrics_avg_latency():
    metrics = SkillPerformanceMetrics()
    metrics.total_invocations = 5
    metrics.total_latency_ms = 500.0

    assert metrics.avg_latency_ms == 100.0


def test_self_improving_engine_record_invocation(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path)

    engine.record_invocation("test_skill", success=True, latency_ms=100.0)
    engine.record_invocation("test_skill", success=True, latency_ms=200.0)
    engine.record_invocation("test_skill", success=False, latency_ms=50.0)

    metrics = engine.get_metrics("test_skill")
    assert metrics.total_invocations == 3
    assert metrics.successful_invocations == 2
    assert metrics.failed_invocations == 1
    assert metrics.total_latency_ms == 350.0


def test_self_improving_engine_user_satisfaction(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path)

    engine.record_invocation("skill", success=True, latency_ms=100.0, user_satisfaction=0.8)
    engine.record_invocation("skill", success=True, latency_ms=100.0, user_satisfaction=0.6)

    metrics = engine.get_metrics("skill")
    assert metrics.user_satisfaction_score == pytest.approx(0.7, rel=0.01)


def test_self_improving_engine_analyze_healthy_skill(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path, min_invocations_for_refinement=3)

    # Record successful invocations with good satisfaction
    for _ in range(5):
        engine.record_invocation("healthy_skill", success=True, latency_ms=100.0, user_satisfaction=0.9)

    health = engine.analyze_skill_health("healthy_skill")
    assert health["health_status"] == "healthy"
    assert len(health["issues"]) == 0


def test_self_improving_engine_analyze_degraded_skill(tmp_path):
    engine = SelfImprovingSkillEngine(
        tmp_path,
        min_invocations_for_refinement=3,
        min_success_rate_threshold=0.8,
    )

    # Record mixed invocations (60% success rate)
    for _ in range(6):
        engine.record_invocation("degraded_skill", success=True, latency_ms=100.0)
    for _ in range(4):
        engine.record_invocation("degraded_skill", success=False, latency_ms=100.0)

    health = engine.analyze_skill_health("degraded_skill")
    assert health["health_status"] == "degraded"
    assert any("success rate" in issue.lower() for issue in health["issues"])


def test_self_improving_engine_analyze_slow_skill(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path, min_invocations_for_refinement=3)

    # Record slow invocations
    for _ in range(5):
        engine.record_invocation("slow_skill", success=True, latency_ms=6000.0)

    health = engine.analyze_skill_health("slow_skill")
    assert health["health_status"] == "slow"
    assert any("latency" in issue.lower() for issue in health["issues"])


def test_self_improving_engine_analyze_insufficient_data(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path, min_invocations_for_refinement=10)

    # Record only 2 invocations
    engine.record_invocation("new_skill", success=True, latency_ms=100.0)
    engine.record_invocation("new_skill", success=True, latency_ms=100.0)

    health = engine.analyze_skill_health("new_skill")
    assert health["health_status"] == "insufficient_data"


def test_self_improving_engine_suggest_refinement(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path, min_invocations_for_refinement=3)

    for _ in range(5):
        engine.record_invocation("test_skill", success=True, latency_ms=100.0)

    # Skill content with missing sections
    skill_content = "# Test Skill\n\nThis is a test skill with [TODO] placeholders."

    result = engine.suggest_skill_refinement("test_skill", skill_content)

    assert "refinement_suggestions" in result
    assert any("Description" in s for s in result["refinement_suggestions"])


def test_self_improving_engine_record_evolution(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path)

    record = engine.record_evolution(
        skill_name="test_skill",
        version="1.1.0",
        evolution_type="refined",
        changes="Added error handling examples",
        metrics={"success_rate": 0.9},
    )

    assert record.skill_name == "test_skill"
    assert record.version == "1.1.0"
    assert record.evolution_type == "refined"

    # Check history
    history = engine.get_evolution_history("test_skill")
    assert len(history) == 1
    assert history[0].skill_name == "test_skill"


def test_self_improving_engine_evolution_history_persists(tmp_path):
    engine1 = SelfImprovingSkillEngine(tmp_path)

    engine1.record_evolution(
        skill_name="persisted_skill",
        version="1.0.0",
        evolution_type="created",
        changes="Initial creation",
    )

    # Create new engine instance
    engine2 = SelfImprovingSkillEngine(tmp_path)

    history = engine2.get_evolution_history("persisted_skill")
    assert len(history) == 1
    assert history[0].skill_name == "persisted_skill"


@pytest.mark.asyncio
async def test_self_improving_engine_health_check(tmp_path):
    engine = SelfImprovingSkillEngine(tmp_path, min_invocations_for_refinement=3)

    # Record for multiple skills
    for _ in range(5):
        engine.record_invocation("skill_a", success=True, latency_ms=100.0)
    for _ in range(3):
        engine.record_invocation("skill_b", success=False, latency_ms=100.0)

    result = await engine.run_health_check()

    assert "summary" in result
    assert result["summary"]["total_skills"] == 2
    assert "details" in result
    assert "skill_a" in result["details"]
    assert "skill_b" in result["details"]
