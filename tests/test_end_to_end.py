import asyncio

from revenue_system.orchestration.demo_flow import run_demo


def test_vertical_slice_runs_for_both_segments():
    output = asyncio.run(run_demo("replay"))
    assert any("[brand]" in line for line in output)
    assert any("[publisher]" in line for line in output)
    assert any("[safety] label=suspicious flagged=True" in line for line in output)
    assert any("[io] valid=True" in line for line in output)

