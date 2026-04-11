import pytest

from metagpt.actions import UserRequirement
from metagpt.logs import logger
from metagpt.roles.di.role_zero import RoleZero
from metagpt.schema import Message


@pytest.mark.asyncio
async def test_model_validators():
    """Test all model validators"""
    role = RoleZero()
    # Test set_plan_and_tool
    assert role.react_mode == "react"
    assert role.planner is not None

    # Test set_tool_execution
    assert "Plan.append_task" in role.tool_execution_map
    assert "RoleZero.ask_human" in role.tool_execution_map

    # Test set_longterm_memory
    assert role.rc.memory is not None


@pytest.mark.asyncio
async def test_think_react_cycle():
    """Test the think-react cycle"""
    # Setup test conditions
    role = RoleZero(tools=["Plan"])
    role.rc.todo = True
    role.planner.plan.goal = "Test goal"
    role.respond_language = "English"

    # Test _think
    result = await role._think()
    assert result is True

    role.rc.news = [Message(content="Test", cause_by=UserRequirement())]
    result = await role._react()
    logger.info(result)
    assert isinstance(result, Message)


@pytest.mark.asyncio
async def test_tool_input_guardrails_block_command():
    blocked_commands = []

    def _input_guardrail(tool_call_data: dict, agent_name: str) -> bool:
        blocked_commands.append((tool_call_data["command_name"], agent_name))
        return tool_call_data["command_name"] != "Danger.run"

    role = RoleZero(tool_input_guardrails=[_input_guardrail])
    role.tool_execution_map = {
        "Safe.run": lambda text: text,
        "Danger.run": lambda text: text,
    }

    outputs = await role._run_commands(
        [
            {"command_name": "Safe.run", "args": {"text": "ok"}},
            {"command_name": "Danger.run", "args": {"text": "blocked"}},
        ]
    )

    assert "Command Safe.run executed: ok" in outputs
    assert "Command Danger.run executed: blocked by tool input guardrails." in outputs
    assert blocked_commands == [("Safe.run", role.name), ("Danger.run", role.name)]


@pytest.mark.asyncio
async def test_tool_output_guardrails_block_output():
    def output_guardrail(tool_call_data: dict, tool_output, agent_name: str) -> bool:
        return "secret" not in str(tool_output)

    role = RoleZero(tool_output_guardrails=[output_guardrail])
    role.tool_execution_map = {
        "Echo.run": lambda text: text,
    }

    outputs = await role._run_commands(
        [
            {"command_name": "Echo.run", "args": {"text": "secret-token"}},
        ]
    )

    assert "Command Echo.run executed: output blocked by tool output guardrails." in outputs
    assert "secret-token" not in outputs


@pytest.mark.asyncio
async def test_multiple_tool_input_guardrails_short_circuit_on_false():
    guardrail_calls = []

    def first_guardrail(tool_call_data: dict, agent_name: str) -> bool:
        guardrail_calls.append("first")
        return True

    def second_guardrail(tool_call_data: dict, agent_name: str) -> bool:
        guardrail_calls.append("second")
        return False

    def third_guardrail(tool_call_data: dict, agent_name: str) -> bool:
        guardrail_calls.append("third")
        return True

    role = RoleZero(tool_input_guardrails=[first_guardrail, second_guardrail, third_guardrail])
    role.tool_execution_map = {"Safe.run": lambda text: text}

    outputs = await role._run_commands(
        [
            {"command_name": "Safe.run", "args": {"text": "ok"}},
        ]
    )

    assert "Command Safe.run executed: blocked by tool input guardrails." in outputs
    assert guardrail_calls == ["first", "second"]
