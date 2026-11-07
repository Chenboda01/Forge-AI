from forge.forge_core.subagents import SUBAGENTS
from forge.ui.subagent_session import SubagentSession


def test_new_session_starts_every_agent_fresh() -> None:
    # Given: a newly created subagent session
    session = SubagentSession()

    # Then: it is labeled generation one with each agent idle
    assert session.generation == 1
    for name in SUBAGENTS:
        state = session.state(name)
        assert state.status == "idle"
        assert state.runs == 0
        assert state.last_report == ""
    assert session.ready_count() == len(SUBAGENTS)


def test_session_tracks_runs_and_resets_after_new() -> None:
    # Given: a session with completed, failed, and cancelled runs
    session = SubagentSession()
    session.begin("explore")
    assert session.ready_count() == len(SUBAGENTS) - 1
    session.complete("explore", "report")
    session.fail("reviewer", "boom")
    session.cancel("explore")

    # Then: status and run counts reflect each outcome
    assert session.state("explore").status == "idle"
    assert session.state("explore").runs == 1
    assert session.state("explore").last_report == "report"
    assert session.state("reviewer").status == "error"
    assert session.state("reviewer").runs == 1

    # When: starting a new session clears the state
    session.reset()

    # Then: every agent is fresh again under a new generation
    assert session.generation == 2
    assert session.ready_count() == len(SUBAGENTS)
    assert all(session.state(name).runs == 0 for name in SUBAGENTS)
