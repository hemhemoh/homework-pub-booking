"""Ex5 tools. Four tools the agent uses to research an Edinburgh booking.

Each tool:
  1. Reads its fixture from sample_data/ (DO NOT modify the fixtures).
  2. Logs its arguments and output into _TOOL_CALL_LOG (see integrity.py).
  3. Returns a ToolResult with success=True/False, output=dict, summary=str.

The grader checks for:
  * Correct parallel_safe flags (reads True, generate_flyer False).
  * Every tool's results appear in _TOOL_CALL_LOG.
  * Tools fail gracefully on missing fixtures or bad inputs (ToolError,
    not RuntimeError).
"""

from __future__ import annotations
from pathlib import Path
import json
from .integrity import record_tool_call
from sovereign_agent.session.directory import Session
from sovereign_agent.tools.registry import (
    ToolRegistry,
    ToolResult,
    _RegisteredTool,
    ToolError,
    # SA_TOOL_DEPENDENCY_MISSING,
    # SA_TOOL_INVALID_INPUT,
)

_SAMPLE_DATA = Path(__file__).parent / "sample_data"

# ---------------------------------------------------------------------------
# TODO 1 — venue_search
# ---------------------------------------------------------------------------
def venue_search(near: str, party_size: int, budget_max_gbp: int = 1000) -> ToolResult:
    """Search for Edinburgh venues near <near> that can seat the party.

    Reads sample_data/venues.json. Filters by:
      * open_now == True
      * area contains <near> (case-insensitive substring match)
      * seats_available_evening >= party_size
      * hire_fee_gbp + min_spend_gbp <= budget_max_gbp

    Returns a ToolResult with:
      output: {"near": ..., "party_size": ..., "results": [<venue dicts>], "count": int}
      summary: "venue_search(<near>, party=<N>): <count> result(s)"

    MUST call record_tool_call(...) before returning so the integrity
    check can see what data was produced.
    """
    # TODO 1a: load venues.json. Raise ToolError(SA_TOOL_DEPENDENCY_MISSING)
    #          if the file is absent.
    if not (_SAMPLE_DATA / "venues.json").exists():
        raise ToolError(SA_TOOL_DEPENDENCY_MISSING, "venues.json not found")
    with open(_SAMPLE_DATA / "venues.json", "r") as f:
        venues = json.load(f)
    results = []
    for venue in venues:
        if (
            venue["open_now"]
            and (near.lower() in venue["area"].lower())
            and venue["seats_available_evening"] >= party_size
            and venue["hire_fee_gbp"] + venue["min_spend_gbp"] <= budget_max_gbp
        ):
            results.append(venue)
    record_tool_call("venue_search", {"near": near, "party_size": party_size, "budget_max_gbp": budget_max_gbp}, {"near": near, "party_size": party_size, "results": results, "count": len(results),})
    return ToolResult(success=True, output={"near": near, "party_size": party_size, "results": results, "count": len(results)}, summary=f"venue_search({near}, party={party_size}): {len(results)} result(s)")



# ---------------------------------------------------------------------------
# TODO 2 — get_weather
# ---------------------------------------------------------------------------
def get_weather(city: str, date: str) -> ToolResult:
    """Look up the scripted weather for <city> on <date> (YYYY-MM-DD).

    Reads sample_data/weather.json. Returns:
      output: {"city": str, "date": str, "condition": str, "temperature_c": int, ...}
      summary: "get_weather(<city>, <date>): <condition>, <temp>C"

    If the city or date is not in the fixture, return success=False with
    a clear ToolError (SA_TOOL_INVALID_INPUT). Do NOT raise.

    MUST call record_tool_call(...) before returning.
    """
    with open(_SAMPLE_DATA / "weather.json", "r") as f:
        weather = json.load(f)

    if city not in weather or date not in weather[city]:
        err = ToolError(SA_TOOL_INVALID_INPUT, "city or date not in fixture")
        record_tool_call("get_weather", {"city": city, "date": date}, {"error": str(err)})
        return ToolResult(success=False, output={"city": city, "date": date}, summary=str(err))

    output = {
        "city": city,
        "date": date,
        "condition": weather[city][date]["condition"],
        "temperature_c": weather[city][date]["temperature_c"],
    }

    record_tool_call("get_weather", {"city": city, "date": date}, output)
    return ToolResult(
        success=True,
        output=output,
        summary=(
            f"get_weather({city}, {date}): {weather[city][date]['condition']}, "
            f"{weather[city][date]['temperature_c']}"
        ),
    )

# ---------------------------------------------------------------------------
# TODO 3 — calculate_cost
# ---------------------------------------------------------------------------
def calculate_cost(
    venue_id: str,
    party_size: int,
    duration_hours: int,
    catering_tier: str = "bar_snacks",
) -> ToolResult:
    """Compute the total cost for a booking.

    Formula:
      base_per_head = base_rates_gbp_per_head[catering_tier]
      venue_mult    = venue_modifiers[venue_id]
      subtotal      = base_per_head * venue_mult * party_size * max(1, duration_hours)
      service       = subtotal * service_charge_percent / 100
      total         = subtotal + service + <venue's hire_fee_gbp + min_spend_gbp>
      deposit_rule  = per deposit_policy thresholds

    Returns:
      output: {
        "venue_id": str,
        "party_size": int,
        "duration_hours": int,
        "catering_tier": str,
        "subtotal_gbp": int,
        "service_gbp": int,
        "total_gbp": int,
        "deposit_required_gbp": int,
      }
      summary: "calculate_cost(<venue>, <party>): total £<N>, deposit £<M>"

    MUST call record_tool_call(...) before returning.
    """
    if not (_SAMPLE_DATA/"cost_config.json").exists():
        raise ToolError(SA_TOOL_DEPENDENCY_MISSING, "cost_config.json not found")
    with open(_SAMPLE_DATA / "cost_config.json", "r") as f:
        cost_config = json.load(f)
    if catering_tier not in cost_config["base_rates_gbp_per_head"]:
        raise ToolError(SA_TOOL_INVALID_INPUT, "invalid catering_tier")
    if venue_id not in cost_config["venue_modifiers"]:
        raise ToolError(SA_TOOL_INVALID_INPUT, "invalid venue_id")
    
    base_per_head = cost_config["base_rates_gbp_per_head"][catering_tier]
    venue_mult = cost_config["venue_modifiers"][venue_id]
    subtotal = base_per_head * venue_mult * party_size * max(1, duration_hours)
    service = subtotal * cost_config["service_charge_percent"] / 100
    venue_cost = cost_config["venues"][venue_id]["hire_fee_gbp"] + cost_config["venues"][venue_id]["min_spend_gbp"]
    total = subtotal + service + venue_cost

    deposit_required_gbp = 0
    for threshold in cost_config["deposit_policy"]:
        if total >= threshold["total_gbp_threshold"]:
            deposit_required_gbp = threshold["deposit_required_gbp"]
    
    output = {
        "venue_id": venue_id,
        "party_size": party_size,
        "duration_hours": duration_hours,
        "catering_tier": catering_tier,
        "subtotal_gbp": int(subtotal),
        "service_gbp": int(service),
        "total_gbp": int(total),
        "deposit_required_gbp": int(deposit_required_gbp),
    }

    record_tool_call("calculate_cost", {"venue_id": venue_id, "party_size": party_size, "duration_hours": duration_hours, "catering_tier": catering_tier}, output)
    return ToolResult(success=True, output=output, summary=f"calculate_cost({venue_id}, party={party_size}): total £{int(total)}, deposit £{int(deposit_required_gbp)}")
    


# ---------------------------------------------------------------------------
# TODO 4 — generate_flyer
# ---------------------------------------------------------------------------
def generate_flyer(session: Session, event_details: dict) -> ToolResult:
    """Produce an HTML flyer and write it to workspace/flyer.html.

    event_details is expected to contain at least:
      venue_name, venue_address, date, time, party_size, condition,
      temperature_c, total_gbp, deposit_required_gbp

    Write a self-contained HTML flyer (inline CSS, no external assets). Tag every key fact with data-testid="<n>" so the integrity check can parse it.

    Write a formatted HTML flyer with an H1 title, the event
    facts, a weather summary, and the cost breakdown.

    Returns:
      output: {"path": "workspace/flyer.html", "bytes_written": int}
      summary: "generate_flyer: wrote <path> (<N> chars)"

    MUST call record_tool_call(...) before returning — the integrity
    check compares the flyer's contents against earlier tool outputs.

    IMPORTANT: this tool MUST be registered with parallel_safe=False
    because it writes a file.
    """
    flyer_path = session.workspace_dir / "flyer.html"
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1 {{ color: #333; }}
            .fact {{ margin-bottom: 10px; }}
            .label {{ font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1 data-testid="title">You're Invited!</h1>
        <div class="fact" data-testid="venue_name"><span class="label">Venue:</span> {event_details.get('venue_name', 'N/A')}</div>
        <div class="fact" data-testid="venue_address"><span class="label">Address:</span> {event_details.get('venue_address', 'N/A')}</div>
        <div class="fact" data-testid="date"><span class="label">Date:</span> {event_details.get('date', 'N/A')}</div>
        <div class="fact" data-testid="time"><span class="label">Time:</span> {event_details.get('time', 'N/A')}</div>
        <div class="fact" data-testid="party_size"><span class="label">Party Size:</span> {event_details.get('party_size', 'N/A')}</div>
        <div class="fact" data-testid="condition"><span class="label">Weather:</span> {event_details.get('condition', 'N/A')}</div>
        <div class="fact" data-testid="temperature_c"><span class="label">Temperature:</span> {event_details.get('temperature_c', 'N/A')}°C</div>
        <div class="fact" data-testid="total_gbp"><span class="label">Total Cost:</span> £{event_details.get('total_gbp', 'N/A')}</div>
        <div class="fact" data-testid="deposit_required_gbp"><span class="label ">Deposit Required:</span> £{event_details.get('deposit_required_gbp', 'N/A')}</div>
    </body>
    </html>
    """
    flyer_path.write_text(html_content, encoding="utf-8")
    bytes_written = len(html_content.encode("utf-8")) 
    record_tool_call("generate_flyer", {"event_details": event_details}, {"path": str(flyer_path), "bytes_written": bytes_written})
    return ToolResult(success=True, output={"path": str(flyer_path), "bytes_written": bytes_written}, summary=f"generate_flyer: wrote {flyer_path} ({bytes_written} chars)")


# ---------------------------------------------------------------------------
# Registry builder — DO NOT MODIFY the name, signature, or registration calls.
# The grader imports and calls this to pick up your tools.
# ---------------------------------------------------------------------------
def build_tool_registry(session: Session) -> ToolRegistry:
    """Build a session-scoped tool registry with all four Ex5 tools plus
    the sovereign-agent builtins (read_file, write_file, list_files,
    handoff_to_structured, complete_task).

    DO NOT change the tool names — the tests and grader call them by name.
    """
    from sovereign_agent.tools.builtin import make_builtin_registry

    reg = make_builtin_registry(session)

    # venue_search
    reg.register(
        _RegisteredTool(
            name="venue_search",
            description="Search Edinburgh venues by area, party size, and max budget.",
            fn=venue_search,
            parameters_schema={
                "type": "object",
                "properties": {
                    "near": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "budget_max_gbp": {"type": "integer", "default": 1000},
                },
                "required": ["near", "party_size"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"near": "Haymarket", "party_size": 6, "budget_max_gbp": 800},
                    "output": {"count": 1, "results": [{"id": "haymarket_tap"}]},
                }
            ],
        )
    )

    # get_weather
    reg.register(
        _RegisteredTool(
            name="get_weather",
            description="Get scripted weather for a city on a YYYY-MM-DD date.",
            fn=get_weather,
            parameters_schema={
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "date": {"type": "string"},
                },
                "required": ["city", "date"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # read-only
            examples=[
                {
                    "input": {"city": "Edinburgh", "date": "2026-04-25"},
                    "output": {"condition": "cloudy", "temperature_c": 12},
                }
            ],
        )
    )

    # calculate_cost
    reg.register(
        _RegisteredTool(
            name="calculate_cost",
            description="Compute total cost and deposit for a booking.",
            fn=calculate_cost,
            parameters_schema={
                "type": "object",
                "properties": {
                    "venue_id": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "duration_hours": {"type": "integer"},
                    "catering_tier": {
                        "type": "string",
                        "enum": ["drinks_only", "bar_snacks", "sit_down_meal", "three_course_meal"],
                        "default": "bar_snacks",
                    },
                },
                "required": ["venue_id", "party_size", "duration_hours"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=True,  # pure compute, no shared state
            examples=[
                {
                    "input": {
                        "venue_id": "haymarket_tap",
                        "party_size": 6,
                        "duration_hours": 3,
                    },
                    "output": {"total_gbp": 540, "deposit_required_gbp": 0},
                }
            ],
        )
    )

    # generate_flyer — parallel_safe=False because it writes a file
    def _flyer_adapter(event_details: dict) -> ToolResult:
        return generate_flyer(session, event_details)

    reg.register(
        _RegisteredTool(
            name="generate_flyer",
            description="Write an HTML flyer for the event to workspace/flyer.html.",
            fn=_flyer_adapter,
            parameters_schema={
                "type": "object",
                "properties": {"event_details": {"type": "object"}},
                "required": ["event_details"],
            },
            returns_schema={"type": "object"},
            is_async=False,
            parallel_safe=False,  # writes a file — MUST be False
            examples=[
                {
                    "input": {
                        "event_details": {
                            "venue_name": "Haymarket Tap",
                            "date": "2026-04-25",
                            "party_size": 6,
                        }
                    },
                    "output": {"path": "workspace/flyer.html"},
                }
            ],
        )
    )

    return reg


__all__ = [
    "build_tool_registry",
    "venue_search",
    "get_weather",
    "calculate_cost",
    "generate_flyer",
]
