"""Removing a recipient from a zone campaign: the pure rules, without a database."""

from types import SimpleNamespace

import pytest

from services import campaign_launch, journey
from services.outreach_os import campaign_plan


def test_a_removed_recipient_has_a_plain_label_and_is_never_a_reason_to_wait():
    assert campaign_launch.REMOVED == "removed_by_reviewer"
    assert campaign_plan.exclusion_label(campaign_launch.REMOVED) == "Retiré de cette campagne par vous"
    assert campaign_plan.refusal_kind(campaign_launch.REMOVED) == "stop"  # at send time: never sent, never retried


@pytest.mark.parametrize(
    "status,left",
    [
        (None, False),
        ("scheduled", False),  # planned: its removal cancels it
        ("cancelled", False),
        ("skipped", False),
        ("failed", False),
        ("sending", True),  # in flight: the outcome is unknown, it cannot be recalled
        ("accepted", True),
        ("unknown", True),
    ],
)
def test_only_a_message_that_has_not_left_can_be_taken_back(status, left):
    plan = None if status is None else SimpleNamespace(status=status)
    assert journey._plan_left(plan) is left
